"""
PROJETO APLICADO I - UniSENAI Florianópolis | Empresa parceira: Schulz S.A.
AV03 - Construção do MVP (Parte 1)

Arquivo: 04_classes.py
Classes de domínio em POO (Tecnico, Equipamento, Medicao), classe de conexão
com o SQLite (ConexaoSQLite) e classes de persistência com CRUD (DAOs).

Organização do módulo:
    1. Exceções da aplicação ..... ErroSistema e subclasses
    2. Saneamento de dados ....... regras de ETL definidas na AV01 (seção 3.1)
    3. Camada de domínio ......... EntidadeBase -> Tecnico, Equipamento, Medicao
                                   EnsaioCalibracao (agrupa as medições de um ensaio)
    4. Camada de persistência .... ConexaoSQLite, DAOBase -> TecnicoDAO,
                                   EquipamentoDAO, MedicaoDAO; RelatorioDAO (JOINs)
    5. Camada de serviço ......... ServicoCalibracao (regras entre entidades)

Requisitos: Python 3.10+ e somente a biblioteca padrão (módulo sqlite3).
"""
from __future__ import annotations

import calendar
import re
import sqlite3
import unicodedata
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Generic, Iterator, Mapping, Optional, TypeVar, Union

# O SQLite não tem tipo DECIMAL nem DATE. Valores metrológicos são gravados como
# texto (ex.: "6.0787295") para não sofrer o arredondamento binário do REAL, e
# datas no formato ISO 8601 ("2026-11-03"). Os adaptadores abaixo permitem passar
# Decimal e date diretamente como parâmetros das consultas.
sqlite3.register_adapter(Decimal, str)
sqlite3.register_adapter(date, date.isoformat)


# =============================================================================
# 1. EXCEÇÕES DA APLICAÇÃO
# =============================================================================
class ErroSistema(Exception):
    """Classe base de todas as exceções do sistema de calibração."""


class ErroValidacao(ErroSistema):
    """Um atributo recebeu valor fora do domínio permitido."""


class ErroRegraNegocio(ErroSistema):
    """Uma regra de negócio homologada na AV01 foi violada."""


class ErroPersistencia(ErroSistema):
    """Falha ao ler ou gravar no banco de dados SQLite."""


class ErroRegistroDuplicado(ErroPersistencia):
    """Violação de restrição UNIQUE (ex.: matrícula ou TAG já cadastrada)."""


class ErroIntegridadeReferencial(ErroPersistencia):
    """Violação de chave estrangeira (registro vinculado ou ID inexistente)."""


class ErroRegistroNaoEncontrado(ErroPersistencia):
    """Operação sobre um ID que não existe no banco."""


# =============================================================================
# 2. SANEAMENTO DE DADOS (regras de ETL da AV01, seção 3.1)
# =============================================================================
# Valores-sentinela usados nas planilhas da Schulz para representar "vazio".
SENTINELAS_NULO = {"", "-", "--", "---", "----", "-----", "------",
                   "00/00/0000", "NÃO INFORMADO", "NAO INFORMADO"}


def limpar_texto(valor: Any, campo: str, *, obrigatorio: bool = True,
                 tamanho_maximo: int = 150) -> Optional[str]:
    """Remove caracteres de controle, aplica trim, colapsa espaços internos e
    converte sentinelas ("------", "00/00/0000", "Não informado") em None."""
    texto = "" if valor is None else unicodedata.normalize("NFC", str(valor))
    texto = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    if texto.upper() in SENTINELAS_NULO:
        texto = ""
    if not texto:
        if obrigatorio:
            raise ErroValidacao(f"{campo} é obrigatório.")
        return None
    if len(texto) > tamanho_maximo:
        raise ErroValidacao(f"{campo} excede {tamanho_maximo} caracteres.")
    return texto


def para_decimal(valor: Any, campo: str) -> Decimal:
    """Converte para Decimal aceitando o formato das planilhas da Schulz.

    "20,4°" -> Decimal("20.4") | "6,0787295" -> Decimal("6.0787295").
    float é convertido via str() para não herdar o erro binário (0.1 -> "0.1").
    """
    if isinstance(valor, bool):
        raise ErroValidacao(f"{campo}: valor booleano não é numérico.")
    if isinstance(valor, Decimal):
        numero = valor
    elif isinstance(valor, (int, float)):
        numero = Decimal(str(valor))
    elif isinstance(valor, str):
        texto = re.sub(r"\s|°C|°", "", valor).replace(",", ".")
        try:
            numero = Decimal(texto)
        except InvalidOperation:
            raise ErroValidacao(f"{campo}: '{valor}' não é um número válido.") from None
    else:
        raise ErroValidacao(f"{campo}: tipo {type(valor).__name__} não é numérico.")
    if not numero.is_finite():
        raise ErroValidacao(f"{campo}: o valor precisa ser finito.")
    return numero


def para_data(valor: Any, campo: str, *, obrigatorio: bool = True) -> Optional[date]:
    """Aceita date, datetime, "AAAA-MM-DD" ou "DD/MM/AAAA"; "00/00/0000" vira None."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = limpar_texto(valor, campo, obrigatorio=obrigatorio, tamanho_maximo=10)
    if texto is None:
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ErroValidacao(f"{campo}: '{texto}' não é uma data válida.")


def normalizar_parametro(nome: Any) -> str:
    """Padroniza o nome do parâmetro medido (AV01, seção 3.1).

    Maiúsculas, sem acentos e com "_" como separador. Parâmetros com prefixo de
    ponto ("62P_") são mantidos; os demais recebem o prefixo fixo "REF_".
        "62P_DIÂMETRO 1"  -> "62P_DIAMETRO_1"
        "PLANICIDADE_REF" -> "REF_PLANICIDADE"
    """
    texto = limpar_texto(nome, "Parâmetro", tamanho_maximo=80)
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto)
                         if not unicodedata.combining(c))
    padrao = re.sub(r"[^A-Z0-9]+", "_", sem_acento.upper()).strip("_")
    if not padrao:
        raise ErroValidacao(f"Parâmetro '{nome}' não contém letras ou números.")
    if not re.match(r"^\d+P_", padrao):
        padrao = "REF_" + re.sub(r"^REF_|_REF$", "", padrao)
    return padrao


def somar_meses(data_base: date, meses: int) -> date:
    """Soma meses ajustando para o último dia do mês (31/01 + 1 mês = 28/02)."""
    total = data_base.month - 1 + meses
    ano, mes = data_base.year + total // 12, total % 12 + 1
    return date(ano, mes, min(data_base.day, calendar.monthrange(ano, mes)[1]))


def _exigir_bool(valor: Any, campo: str) -> bool:
    if not isinstance(valor, bool):
        raise ErroValidacao(f"{campo} deve ser verdadeiro ou falso.")
    return valor


# =============================================================================
# 3. CAMADA DE DOMÍNIO
# =============================================================================
class EntidadeBase(ABC):
    """Superclasse abstrata das entidades persistidas.

    Centraliza a identidade do objeto (ID atribuído uma única vez, pelo banco) e
    define o contrato que toda entidade cumpre: validar() e resumo().
    """

    def __init__(self, id_entidade: Optional[int] = None) -> None:
        self._id: Optional[int] = None
        if id_entidade is not None:
            self.atribuir_id(id_entidade)

    @property
    def id(self) -> Optional[int]:
        return self._id

    @property
    def persistido(self) -> bool:
        return self._id is not None

    def atribuir_id(self, novo_id: int) -> None:
        """Define o ID gerado pelo banco. Depois de atribuído, não muda mais."""
        if isinstance(novo_id, bool) or not isinstance(novo_id, int) or novo_id <= 0:
            raise ErroValidacao("ID deve ser um inteiro positivo.")
        if self._id is not None and self._id != novo_id:
            raise ErroValidacao(f"{type(self).__name__} já possui o ID {self._id}.")
        self._id = novo_id

    def desvincular_id(self) -> None:
        """Uso da camada de persistência: desfaz o ID quando a transação sofre ROLLBACK."""
        self._id = None

    @abstractmethod
    def validar(self) -> None:
        """Verifica as regras que envolvem mais de um atributo."""

    @abstractmethod
    def resumo(self) -> str:
        """Descrição curta usada em listagens (sobrescrita em cada subclasse)."""

    def __str__(self) -> str:
        return self.resumo()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} id={self._id} {self.resumo()}>"


class Tecnico(EntidadeBase):
    """Profissional do laboratório de metrologia (tabela `tecnicos`)."""

    PERFIL_METROLOGISTA = "METROLOGISTA"
    PERFIL_SIGNATARIO = "SIGNATARIO"
    PERFIL_QUALIDADE = "QUALIDADE"
    PERFIS = (PERFIL_METROLOGISTA, PERFIL_SIGNATARIO, PERFIL_QUALIDADE)
    _PADRAO_MATRICULA = re.compile(r"^\d{4,6}-\d$")  # formato da AV01, ex.: 16858-0
    _PADRAO_NOME = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ' .-]+$")

    def __init__(self, matricula: str, nome: str, setor: str,
                 perfil: str = PERFIL_METROLOGISTA, ativo: bool = True,
                 id_tecnico: Optional[int] = None) -> None:
        super().__init__(id_tecnico)
        self.matricula = matricula
        self.nome = nome
        self.setor = setor
        self.perfil = perfil
        self.ativo = ativo
        self.validar()

    @property
    def id_tecnico(self) -> Optional[int]:
        return self.id

    @property
    def matricula(self) -> str:
        return self._matricula

    @matricula.setter
    def matricula(self, valor: str) -> None:
        texto = limpar_texto(valor, "Matrícula", tamanho_maximo=10)
        if not self._PADRAO_MATRICULA.match(texto):
            raise ErroValidacao(f"Matrícula '{texto}' fora do padrão 99999-9.")
        self._matricula = texto

    @property
    def nome(self) -> str:
        return self._nome

    @nome.setter
    def nome(self, valor: str) -> None:
        texto = limpar_texto(valor, "Nome do técnico", tamanho_maximo=100)
        if len(texto) < 3 or not self._PADRAO_NOME.match(texto):
            raise ErroValidacao(f"Nome do técnico inválido: '{texto}'.")
        self._nome = texto

    @property
    def setor(self) -> str:
        return self._setor

    @setor.setter
    def setor(self, valor: str) -> None:
        self._setor = limpar_texto(valor, "Setor", tamanho_maximo=80)

    @property
    def perfil(self) -> str:
        return self._perfil

    @perfil.setter
    def perfil(self, valor: str) -> None:
        texto = limpar_texto(valor, "Perfil").upper()
        if texto not in self.PERFIS:
            raise ErroValidacao(f"Perfil '{texto}' inválido. Use: {', '.join(self.PERFIS)}.")
        self._perfil = texto

    @property
    def ativo(self) -> bool:
        return self._ativo

    @ativo.setter
    def ativo(self, valor: bool) -> None:
        self._ativo = _exigir_bool(valor, "Ativo")

    def validar(self) -> None:
        """As regras do técnico são de atributo único e já ficam nos setters."""

    def pode_registrar_medicao(self) -> bool:
        """RN10 (AV01): somente metrologista ativo registra resultados de medição."""
        return self._ativo and self._perfil == self.PERFIL_METROLOGISTA

    def resumo(self) -> str:
        return f"{self._matricula} {self._nome} ({self._perfil})"


class Equipamento(EntidadeBase):
    """Instrumento de medição ou dispositivo de controle (tabela `equipamentos`)."""

    UNIDADES = ("mm", "µm", "pol")
    DIAS_ALERTA_VENCIMENTO = 15  # AV01, UC05: alertar 15 dias antes do vencimento
    SITUACAO_EM_DIA = "EM DIA"
    SITUACAO_A_VENCER = "A VENCER"
    SITUACAO_VENCIDA = "VENCIDA"
    SITUACAO_SEM_CALIBRACAO = "SEM CALIBRACAO"
    _PADRAO_TAG = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{2,29}$")

    def __init__(self, codigo_tag: str, descricao: str, fabricante: str,
                 resolucao: Any, departamento: str, periodicidade_meses: int = 12,
                 modelo: Optional[str] = None, numero_serie: Optional[str] = None,
                 unidade: str = "mm", data_ultima_calibracao: Any = None,
                 ativo: bool = True, id_equipamento: Optional[int] = None) -> None:
        super().__init__(id_equipamento)
        self.codigo_tag = codigo_tag
        self.descricao = descricao
        self.fabricante = fabricante
        self.modelo = modelo
        self.numero_serie = numero_serie
        self.resolucao = resolucao
        self.unidade = unidade
        self.departamento = departamento
        self.periodicidade_meses = periodicidade_meses
        self.data_ultima_calibracao = data_ultima_calibracao
        self.ativo = ativo
        self.validar()

    @property
    def id_equipamento(self) -> Optional[int]:
        return self.id

    @property
    def codigo_tag(self) -> str:
        return self._codigo_tag

    @codigo_tag.setter
    def codigo_tag(self, valor: str) -> None:
        texto = limpar_texto(valor, "Código TAG", tamanho_maximo=30).upper()
        if not self._PADRAO_TAG.match(texto):
            raise ErroValidacao(f"Código TAG '{texto}' inválido (use letras, números, '.' e '-').")
        self._codigo_tag = texto

    @property
    def descricao(self) -> str:
        return self._descricao

    @descricao.setter
    def descricao(self, valor: str) -> None:
        self._descricao = limpar_texto(valor, "Descrição", tamanho_maximo=150)

    @property
    def fabricante(self) -> str:
        return self._fabricante

    @fabricante.setter
    def fabricante(self, valor: str) -> None:
        # "Não consta" é valor de negócio válido (AV01, dicionário de dados).
        self._fabricante = limpar_texto(valor, "Fabricante", tamanho_maximo=80)

    @property
    def modelo(self) -> Optional[str]:
        return self._modelo

    @modelo.setter
    def modelo(self, valor: Optional[str]) -> None:
        self._modelo = limpar_texto(valor, "Modelo", obrigatorio=False, tamanho_maximo=80)

    @property
    def numero_serie(self) -> Optional[str]:
        return self._numero_serie

    @numero_serie.setter
    def numero_serie(self, valor: Optional[str]) -> None:
        self._numero_serie = limpar_texto(valor, "Número de série", obrigatorio=False,
                                          tamanho_maximo=50)

    @property
    def resolucao(self) -> Decimal:
        return self._resolucao

    @resolucao.setter
    def resolucao(self, valor: Any) -> None:
        numero = para_decimal(valor, "Resolução")
        if not Decimal("0") < numero <= Decimal("1"):
            raise ErroValidacao(f"Resolução {numero} fora da faixa (0; 1].")
        self._resolucao = numero

    @property
    def unidade(self) -> str:
        return self._unidade

    @unidade.setter
    def unidade(self, valor: str) -> None:
        texto = limpar_texto(valor, "Unidade", tamanho_maximo=5)
        if texto not in self.UNIDADES:
            raise ErroValidacao(f"Unidade '{texto}' inválida. Use: {', '.join(self.UNIDADES)}.")
        self._unidade = texto

    @property
    def departamento(self) -> str:
        return self._departamento

    @departamento.setter
    def departamento(self, valor: str) -> None:
        self._departamento = limpar_texto(valor, "Departamento", tamanho_maximo=80)

    @property
    def periodicidade_meses(self) -> int:
        return self._periodicidade_meses

    @periodicidade_meses.setter
    def periodicidade_meses(self, valor: int) -> None:
        if isinstance(valor, bool) or not isinstance(valor, int) or not 1 <= valor <= 60:
            raise ErroValidacao("Periodicidade deve ser um inteiro entre 1 e 60 meses.")
        self._periodicidade_meses = valor

    @property
    def data_ultima_calibracao(self) -> Optional[date]:
        return self._data_ultima_calibracao

    @data_ultima_calibracao.setter
    def data_ultima_calibracao(self, valor: Any) -> None:
        data_cal = para_data(valor, "Data da última calibração", obrigatorio=False)
        if data_cal and data_cal > date.today():
            raise ErroValidacao("Data da última calibração não pode estar no futuro.")
        self._data_ultima_calibracao = data_cal

    @property
    def ativo(self) -> bool:
        return self._ativo

    @ativo.setter
    def ativo(self, valor: bool) -> None:
        self._ativo = _exigir_bool(valor, "Ativo")

    def validar(self) -> None:
        """As regras do equipamento são de atributo único e já ficam nos setters."""

    def proxima_calibracao(self) -> Optional[date]:
        """RN02 (AV01): vencimento = última calibração + periodicidade em meses."""
        if self._data_ultima_calibracao is None:
            return None
        return somar_meses(self._data_ultima_calibracao, self._periodicidade_meses)

    def dias_para_vencimento(self, hoje: Optional[date] = None) -> Optional[int]:
        proxima = self.proxima_calibracao()
        return None if proxima is None else (proxima - (hoje or date.today())).days

    def situacao_calibracao(self, hoje: Optional[date] = None) -> str:
        dias = self.dias_para_vencimento(hoje)
        if dias is None:
            return self.SITUACAO_SEM_CALIBRACAO
        if dias < 0:
            return self.SITUACAO_VENCIDA
        if dias <= self.DIAS_ALERTA_VENCIMENTO:
            return self.SITUACAO_A_VENCER
        return self.SITUACAO_EM_DIA

    def calibracao_vencida(self, hoje: Optional[date] = None) -> bool:
        return self.situacao_calibracao(hoje) in (self.SITUACAO_VENCIDA,
                                                  self.SITUACAO_SEM_CALIBRACAO)

    def registrar_calibracao(self, data_calibracao: Any) -> None:
        """Atualiza a última calibração após um ensaio aprovado (RN02/RN06 da AV01)."""
        data_cal = para_data(data_calibracao, "Data da calibração")
        if self._data_ultima_calibracao and data_cal < self._data_ultima_calibracao:
            raise ErroRegraNegocio("Data da calibração é anterior à última já registrada.")
        self.data_ultima_calibracao = data_cal

    def resumo(self) -> str:
        return f"{self._codigo_tag} {self._descricao} [{self._departamento}]"


class Medicao(EntidadeBase):
    """Ensaio de calibração de um parâmetro de um equipamento (tabela `medicoes`).

    Encapsula a validação do status APROVADO/REPROVADO a partir das tolerâncias e
    do valor obtido, pela regra de soma algébrica (RN05 da AV01):
        erro         = valor_obtido - valor_nominal
        faixa aceita = [nominal + tolerancia_inferior ; nominal + tolerancia_superior]
        status       = APROVADO se o valor obtido estiver na faixa (limites inclusos)
    O status é calculado (property) e por isso nunca fica desatualizado.
    """

    STATUS_APROVADO = "APROVADO"
    STATUS_REPROVADO = "REPROVADO"
    TEMPERATURA_MIN = Decimal("15")
    TEMPERATURA_MAX = Decimal("30")  # mesma faixa do CHECK definido na AV02

    def __init__(self, equipamento: Equipamento, tecnico: Tecnico, parametro: str,
                 valor_nominal: Any, tolerancia_inferior: Any, tolerancia_superior: Any,
                 valor_obtido: Any, temperatura_c: Any, data_medicao: Any = None,
                 observacao: Optional[str] = None,
                 id_medicao: Optional[int] = None) -> None:
        super().__init__(id_medicao)
        if not isinstance(equipamento, Equipamento):
            raise ErroValidacao("A medição precisa de um objeto Equipamento.")
        if not isinstance(tecnico, Tecnico):
            raise ErroValidacao("A medição precisa de um objeto Tecnico.")
        self._equipamento = equipamento  # associação: a medição pertence a um equipamento
        self._tecnico = tecnico          # associação: e foi executada por um técnico
        self.parametro = parametro
        self.valor_nominal = valor_nominal
        self.definir_tolerancias(tolerancia_inferior, tolerancia_superior)
        self.valor_obtido = valor_obtido
        self.temperatura_c = temperatura_c
        self.data_medicao = date.today() if data_medicao is None else data_medicao
        self.observacao = observacao
        self.validar()

    # --- associações (somente leitura) ---------------------------------------
    @property
    def id_medicao(self) -> Optional[int]:
        return self.id

    @property
    def equipamento(self) -> Equipamento:
        return self._equipamento

    @property
    def tecnico(self) -> Tecnico:
        return self._tecnico

    # --- atributos com validação ----------------------------------------------
    @property
    def parametro(self) -> str:
        return self._parametro

    @parametro.setter
    def parametro(self, valor: str) -> None:
        self._parametro = normalizar_parametro(valor)

    @property
    def valor_nominal(self) -> Decimal:
        return self._valor_nominal

    @valor_nominal.setter
    def valor_nominal(self, valor: Any) -> None:
        self._valor_nominal = para_decimal(valor, "Valor nominal")

    @property
    def tolerancia_inferior(self) -> Decimal:
        return self._tolerancia_inferior

    @property
    def tolerancia_superior(self) -> Decimal:
        return self._tolerancia_superior

    def definir_tolerancias(self, inferior: Any, superior: Any) -> None:
        """Define as duas tolerâncias juntas, garantindo inferior < superior."""
        tol_inf = para_decimal(inferior, "Tolerância inferior")
        tol_sup = para_decimal(superior, "Tolerância superior")
        if tol_inf >= tol_sup:
            raise ErroValidacao(f"Tolerância inferior ({tol_inf}) deve ser menor que a "
                                f"superior ({tol_sup}).")
        self._tolerancia_inferior, self._tolerancia_superior = tol_inf, tol_sup

    @property
    def valor_obtido(self) -> Decimal:
        return self._valor_obtido

    @valor_obtido.setter
    def valor_obtido(self, valor: Any) -> None:
        self._valor_obtido = para_decimal(valor, "Valor obtido")

    @property
    def temperatura_c(self) -> Decimal:
        return self._temperatura_c

    @temperatura_c.setter
    def temperatura_c(self, valor: Any) -> None:
        temperatura = para_decimal(valor, "Temperatura ambiente")
        if not self.TEMPERATURA_MIN <= temperatura <= self.TEMPERATURA_MAX:
            raise ErroValidacao(f"Temperatura {temperatura} °C fora da faixa de ensaio "
                                f"({self.TEMPERATURA_MIN} a {self.TEMPERATURA_MAX} °C).")
        self._temperatura_c = temperatura

    @property
    def data_medicao(self) -> date:
        return self._data_medicao

    @data_medicao.setter
    def data_medicao(self, valor: Any) -> None:
        data_med = para_data(valor, "Data da medição")
        if data_med > date.today():
            raise ErroValidacao("Data da medição não pode estar no futuro.")
        self._data_medicao = data_med

    @property
    def observacao(self) -> Optional[str]:
        return self._observacao

    @observacao.setter
    def observacao(self, valor: Optional[str]) -> None:
        self._observacao = limpar_texto(valor, "Observação", obrigatorio=False,
                                        tamanho_maximo=255)

    # --- lógica de validação da tolerância ------------------------------------
    @property
    def erro(self) -> Decimal:
        """RN05 (AV01): erro pela soma algébrica (valor obtido - valor nominal)."""
        return self._valor_obtido - self._valor_nominal

    @property
    def limite_inferior(self) -> Decimal:
        return self._valor_nominal + self._tolerancia_inferior

    @property
    def limite_superior(self) -> Decimal:
        return self._valor_nominal + self._tolerancia_superior

    def dentro_da_tolerancia(self) -> bool:
        return self.limite_inferior <= self._valor_obtido <= self.limite_superior

    @property
    def status(self) -> str:
        return self.STATUS_APROVADO if self.dentro_da_tolerancia() else self.STATUS_REPROVADO

    def validar(self) -> None:
        """Regra entre atributos: a faixa de tolerância precisa ser válida."""
        if self._tolerancia_inferior >= self._tolerancia_superior:
            raise ErroValidacao("Faixa de tolerância inválida.")

    def resumo(self) -> str:
        return (f"{self._equipamento.codigo_tag} {self._parametro} "
                f"erro={self.erro:+} {self.status}")


class EnsaioCalibracao:
    """Agrupa os pontos medidos de um equipamento numa mesma data (composição:
    as medições são criadas e mantidas pelo ensaio).

    Parecer do ensaio (RN06 da AV01): REPROVADO se qualquer ponto for reprovado.
    """

    def __init__(self, equipamento: Equipamento, tecnico: Tecnico,
                 data_medicao: Any, temperatura_c: Any) -> None:
        self._equipamento = equipamento
        self._tecnico = tecnico
        self._data_medicao = para_data(data_medicao, "Data do ensaio")
        self._temperatura_c = para_decimal(temperatura_c, "Temperatura ambiente")
        self._medicoes: list[Medicao] = []

    @property
    def equipamento(self) -> Equipamento:
        return self._equipamento

    @property
    def tecnico(self) -> Tecnico:
        return self._tecnico

    @property
    def data_medicao(self) -> date:
        return self._data_medicao

    @property
    def medicoes(self) -> tuple[Medicao, ...]:
        return tuple(self._medicoes)

    def adicionar_ponto(self, parametro: str, valor_nominal: Any, tolerancia_inferior: Any,
                        tolerancia_superior: Any, valor_obtido: Any,
                        observacao: Optional[str] = None) -> Medicao:
        medicao = Medicao(self._equipamento, self._tecnico, parametro, valor_nominal,
                          tolerancia_inferior, tolerancia_superior, valor_obtido,
                          self._temperatura_c, self._data_medicao, observacao)
        if any(m.parametro == medicao.parametro for m in self._medicoes):
            raise ErroValidacao(f"Parâmetro {medicao.parametro} já consta neste ensaio.")
        self._medicoes.append(medicao)
        return medicao

    @property
    def pontos_reprovados(self) -> list[Medicao]:
        return [m for m in self._medicoes if m.status == Medicao.STATUS_REPROVADO]

    @property
    def aprovado(self) -> bool:
        return bool(self._medicoes) and not self.pontos_reprovados

    @property
    def parecer(self) -> str:
        return Medicao.STATUS_APROVADO if self.aprovado else Medicao.STATUS_REPROVADO


# =============================================================================
# 4. CAMADA DE PERSISTÊNCIA (SQLite via módulo sqlite3)
# =============================================================================
class ConexaoSQLite:
    """Gerencia a conexão com o SQLite: abertura, chaves estrangeiras, transações,
    criação do esquema e tradução dos erros do banco em exceções do domínio."""

    ESQUEMA_SQL = """
    BEGIN;
    CREATE TABLE IF NOT EXISTS tecnicos (
        id_tecnico   INTEGER PRIMARY KEY AUTOINCREMENT,
        matricula    TEXT    NOT NULL UNIQUE,
        nome         TEXT    NOT NULL CHECK (length(trim(nome)) >= 3),
        setor        TEXT    NOT NULL,
        perfil       TEXT    NOT NULL
                     CHECK (perfil IN ('METROLOGISTA', 'SIGNATARIO', 'QUALIDADE')),
        ativo        INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
        criado_em    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS equipamentos (
        id_equipamento         INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_tag             TEXT    NOT NULL UNIQUE,
        descricao              TEXT    NOT NULL,
        fabricante             TEXT    NOT NULL,
        modelo                 TEXT,
        numero_serie           TEXT,
        resolucao              TEXT    NOT NULL,
        unidade                TEXT    NOT NULL DEFAULT 'mm'
                               CHECK (unidade IN ('mm', 'µm', 'pol')),
        departamento           TEXT    NOT NULL,
        periodicidade_meses    INTEGER NOT NULL CHECK (periodicidade_meses BETWEEN 1 AND 60),
        data_ultima_calibracao TEXT    CHECK (data_ultima_calibracao IS NULL
                                              OR date(data_ultima_calibracao) = data_ultima_calibracao),
        ativo                  INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
        criado_em              TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS medicoes (
        id_medicao           INTEGER PRIMARY KEY AUTOINCREMENT,
        id_equipamento       INTEGER NOT NULL
                             REFERENCES equipamentos (id_equipamento)
                             ON UPDATE CASCADE ON DELETE RESTRICT,
        id_tecnico           INTEGER NOT NULL
                             REFERENCES tecnicos (id_tecnico)
                             ON UPDATE CASCADE ON DELETE RESTRICT,
        data_medicao         TEXT    NOT NULL CHECK (date(data_medicao) = data_medicao),
        parametro            TEXT    NOT NULL,
        valor_nominal        TEXT    NOT NULL,
        tolerancia_inferior  TEXT    NOT NULL,
        tolerancia_superior  TEXT    NOT NULL,
        valor_obtido         TEXT    NOT NULL,
        erro                 TEXT    NOT NULL,
        status               TEXT    NOT NULL CHECK (status IN ('APROVADO', 'REPROVADO')),
        temperatura_c        TEXT    NOT NULL,
        observacao           TEXT,
        criado_em            TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
        -- chave de deduplicação definida na AV01: equipamento + data + parâmetro
        UNIQUE (id_equipamento, data_medicao, parametro)
    );

    CREATE INDEX IF NOT EXISTS idx_medicoes_equipamento ON medicoes (id_equipamento, data_medicao);
    CREATE INDEX IF NOT EXISTS idx_medicoes_tecnico     ON medicoes (id_tecnico);
    CREATE INDEX IF NOT EXISTS idx_medicoes_status      ON medicoes (status);
    COMMIT;
    """

    def __init__(self, caminho: Union[str, Path] = ":memory:") -> None:
        self._caminho = str(caminho)
        self._conexao: Optional[sqlite3.Connection] = None
        self._nivel_transacao = 0
        self._acoes_desfazer: list[Callable[[], None]] = []

    @property
    def caminho(self) -> str:
        return self._caminho

    def abrir(self) -> sqlite3.Connection:
        if self._conexao is None:
            try:
                # isolation_level=None: as transações são abertas explicitamente (BEGIN).
                conexao = sqlite3.connect(self._caminho, isolation_level=None)
                conexao.row_factory = sqlite3.Row
                # O SQLite vem com as chaves estrangeiras DESLIGADAS por padrão.
                conexao.execute("PRAGMA foreign_keys = ON")
            except sqlite3.Error as erro:
                raise ErroPersistencia(f"Não foi possível abrir o banco "
                                       f"'{self._caminho}': {erro}") from erro
            self._conexao = conexao
        return self._conexao

    def fechar(self) -> None:
        if self._conexao is not None:
            self._conexao.close()
            self._conexao = None

    def __enter__(self) -> "ConexaoSQLite":
        self.abrir()
        return self

    def __exit__(self, *_excecao: Any) -> None:
        self.fechar()

    @contextmanager
    def transacao(self) -> Iterator[sqlite3.Connection]:
        """BEGIN ... COMMIT, ou ROLLBACK em caso de erro. Pode ser aninhada: só a
        transação mais externa confirma ou desfaz, o que torna lotes atômicos."""
        conexao = self.abrir()
        externa = self._nivel_transacao == 0
        if externa:
            conexao.execute("BEGIN")
            self._acoes_desfazer = []
        self._nivel_transacao += 1
        try:
            yield conexao
            if externa:
                conexao.execute("COMMIT")
        except BaseException as erro:
            if externa:
                if conexao.in_transaction:
                    conexao.execute("ROLLBACK")
                for acao in reversed(self._acoes_desfazer):
                    acao()  # devolve os objetos em memória ao estado anterior
            if isinstance(erro, sqlite3.Error):
                raise self.traduzir_erro(erro) from erro
            raise
        finally:
            self._nivel_transacao -= 1
            if externa:
                self._acoes_desfazer = []

    def ao_desfazer(self, acao: Callable[[], None]) -> None:
        """Registra o que restaurar em memória se a transação atual sofrer ROLLBACK."""
        if self._nivel_transacao:
            self._acoes_desfazer.append(acao)

    def executar(self, sql: str, parametros: Any = ()) -> sqlite3.Cursor:
        """Executa um comando de escrita (INSERT, UPDATE, DELETE) numa transação."""
        with self.transacao() as conexao:
            return conexao.execute(sql, parametros)

    def consultar(self, sql: str, parametros: Any = ()) -> list[sqlite3.Row]:
        """Executa um SELECT e devolve todas as linhas."""
        try:
            return self.abrir().execute(sql, parametros).fetchall()
        except sqlite3.Error as erro:
            raise self.traduzir_erro(erro) from erro

    def criar_esquema(self) -> None:
        try:
            self.abrir().executescript(self.ESQUEMA_SQL)
        except sqlite3.Error as erro:
            raise self.traduzir_erro(erro) from erro

    def listar_tabelas(self) -> list[str]:
        linhas = self.consultar("SELECT name FROM sqlite_master WHERE type = 'table' "
                                "AND name NOT LIKE 'sqlite_%' ORDER BY name")
        return [linha["name"] for linha in linhas]

    def chaves_estrangeiras_ativas(self) -> bool:
        return self.consultar("PRAGMA foreign_keys")[0][0] == 1

    @staticmethod
    def traduzir_erro(erro: sqlite3.Error) -> ErroPersistencia:
        """Converte a exceção do sqlite3 numa exceção do domínio com mensagem clara."""
        mensagem = str(erro)
        detalhe = mensagem.split(":", 1)[1].strip() if ":" in mensagem else mensagem
        if isinstance(erro, sqlite3.IntegrityError):
            if mensagem.startswith("UNIQUE constraint failed"):
                return ErroRegistroDuplicado(f"Já existe registro com o mesmo valor em {detalhe}.")
            if mensagem.startswith("FOREIGN KEY constraint failed"):
                return ErroIntegridadeReferencial(
                    "Operação bloqueada pela integridade referencial: o registro está "
                    "vinculado a outro ou referencia um ID inexistente.")
            if mensagem.startswith("CHECK constraint failed"):
                return ErroPersistencia(f"Valor rejeitado pela restrição CHECK do banco ({detalhe}).")
            if mensagem.startswith("NOT NULL constraint failed"):
                return ErroPersistencia(f"Campo obrigatório não informado: {detalhe}.")
        if isinstance(erro, sqlite3.OperationalError):
            return ErroPersistencia(f"Falha operacional no SQLite: {mensagem}.")
        return ErroPersistencia(f"Erro de banco de dados: {mensagem}.")


E = TypeVar("E", bound=EntidadeBase)


class DAOBase(ABC, Generic[E]):
    """Superclasse dos DAOs (Data Access Object).

    O CRUD é implementado uma única vez aqui (padrão Template Method). Cada
    subclasse informa a tabela e implementa os dois ganchos de conversão:
    _para_linha (objeto -> colunas) e _para_objeto (linha -> objeto).
    Nomes de tabela e coluna vêm de constantes do código; valores informados
    pelo usuário entram sempre como parâmetros (?, :nome), nunca concatenados.
    """

    TABELA = ""
    CHAVE = ""
    CHAVE_SELECT = ""  # chave qualificada no SELECT (ex.: "m.id_medicao" com JOIN)
    ORDENACAO = ""

    def __init__(self, conexao: ConexaoSQLite) -> None:
        self._db = conexao

    @abstractmethod
    def _para_linha(self, entidade: E) -> dict[str, Any]:
        """Converte o objeto em {coluna: valor} para INSERT e UPDATE."""

    @abstractmethod
    def _para_objeto(self, linha: Mapping[str, Any]) -> E:
        """Reconstrói o objeto de domínio a partir de uma linha do SELECT."""

    def _sql_select(self) -> str:
        """SELECT base das consultas. Subclasses podem sobrescrever (ex.: com JOIN)."""
        return f"SELECT * FROM {self.TABELA}"

    def _listar_onde(self, condicao: str = "", parametros: Any = ()) -> list[E]:
        sql = self._sql_select()
        if condicao:
            sql += f" WHERE {condicao}"
        if self.ORDENACAO:
            sql += f" ORDER BY {self.ORDENACAO}"
        return [self._para_objeto(linha) for linha in self._db.consultar(sql, parametros)]

    # --- CRUD -----------------------------------------------------------------
    def inserir(self, entidade: E) -> int:
        """INSERT: grava o objeto e atribui a ele o ID gerado pelo banco."""
        if entidade.persistido:
            raise ErroValidacao(f"{entidade!r} já foi inserido; use atualizar().")
        entidade.validar()
        dados = self._para_linha(entidade)
        colunas = ", ".join(dados)
        marcadores = ", ".join(f":{coluna}" for coluna in dados)
        with self._db.transacao() as conexao:
            cursor = conexao.execute(
                f"INSERT INTO {self.TABELA} ({colunas}) VALUES ({marcadores})", dados)
            entidade.atribuir_id(cursor.lastrowid)
            self._db.ao_desfazer(entidade.desvincular_id)
        return entidade.id

    def buscar_por_id(self, id_entidade: int) -> Optional[E]:
        """SELECT por chave primária; devolve None se não existir."""
        encontrados = self._listar_onde(f"{self.CHAVE_SELECT or self.CHAVE} = ?",
                                        (id_entidade,))
        return encontrados[0] if encontrados else None

    def obter(self, id_entidade: int) -> E:
        """Como buscar_por_id, mas lança ErroRegistroNaoEncontrado se não existir."""
        entidade = self.buscar_por_id(id_entidade)
        if entidade is None:
            raise ErroRegistroNaoEncontrado(f"{self.TABELA}: ID {id_entidade} não encontrado.")
        return entidade

    def listar(self) -> list[E]:
        return self._listar_onde()

    def atualizar(self, entidade: E) -> None:
        """UPDATE de todas as colunas mapeadas, pela chave primária."""
        if not entidade.persistido:
            raise ErroValidacao(f"{entidade!r} ainda não foi inserido; use inserir().")
        entidade.validar()
        dados = self._para_linha(entidade)
        atribuicoes = ", ".join(f"{coluna} = :{coluna}" for coluna in dados)
        dados["_id"] = entidade.id
        with self._db.transacao() as conexao:
            cursor = conexao.execute(
                f"UPDATE {self.TABELA} SET {atribuicoes} WHERE {self.CHAVE} = :_id", dados)
            if cursor.rowcount == 0:
                raise ErroRegistroNaoEncontrado(f"{self.TABELA}: ID {entidade.id} não encontrado.")

    def excluir(self, id_entidade: int) -> None:
        """DELETE pela chave primária (bloqueado pelo banco se houver vínculos)."""
        with self._db.transacao() as conexao:
            cursor = conexao.execute(f"DELETE FROM {self.TABELA} WHERE {self.CHAVE} = ?",
                                     (id_entidade,))
            if cursor.rowcount == 0:
                raise ErroRegistroNaoEncontrado(f"{self.TABELA}: ID {id_entidade} não encontrado.")

    def contar(self) -> int:
        return self._db.consultar(f"SELECT COUNT(*) FROM {self.TABELA}")[0][0]


class TecnicoDAO(DAOBase[Tecnico]):
    TABELA, CHAVE, ORDENACAO = "tecnicos", "id_tecnico", "nome"

    def _para_linha(self, tecnico: Tecnico) -> dict[str, Any]:
        return {"matricula": tecnico.matricula, "nome": tecnico.nome,
                "setor": tecnico.setor, "perfil": tecnico.perfil,
                "ativo": int(tecnico.ativo)}

    def _para_objeto(self, linha: Mapping[str, Any]) -> Tecnico:
        return Tecnico(linha["matricula"], linha["nome"], linha["setor"], linha["perfil"],
                       bool(linha["ativo"]), id_tecnico=linha["id_tecnico"])

    def buscar_por_matricula(self, matricula: str) -> Optional[Tecnico]:
        encontrados = self._listar_onde("matricula = ?", (matricula,))
        return encontrados[0] if encontrados else None

    def listar_por_perfil(self, perfil: str, apenas_ativos: bool = True) -> list[Tecnico]:
        condicao = "perfil = ?" + (" AND ativo = 1" if apenas_ativos else "")
        return self._listar_onde(condicao, (perfil.upper(),))


class EquipamentoDAO(DAOBase[Equipamento]):
    TABELA, CHAVE, ORDENACAO = "equipamentos", "id_equipamento", "codigo_tag"

    def _para_linha(self, equipamento: Equipamento) -> dict[str, Any]:
        return {"codigo_tag": equipamento.codigo_tag, "descricao": equipamento.descricao,
                "fabricante": equipamento.fabricante, "modelo": equipamento.modelo,
                "numero_serie": equipamento.numero_serie,
                "resolucao": equipamento.resolucao, "unidade": equipamento.unidade,
                "departamento": equipamento.departamento,
                "periodicidade_meses": equipamento.periodicidade_meses,
                "data_ultima_calibracao": equipamento.data_ultima_calibracao,
                "ativo": int(equipamento.ativo)}

    def _para_objeto(self, linha: Mapping[str, Any]) -> Equipamento:
        return Equipamento(linha["codigo_tag"], linha["descricao"], linha["fabricante"],
                           Decimal(linha["resolucao"]), linha["departamento"],
                           linha["periodicidade_meses"], linha["modelo"],
                           linha["numero_serie"], linha["unidade"],
                           linha["data_ultima_calibracao"], bool(linha["ativo"]),
                           id_equipamento=linha["id_equipamento"])

    def buscar_por_tag(self, codigo_tag: str) -> Optional[Equipamento]:
        encontrados = self._listar_onde("codigo_tag = ?", (codigo_tag.strip().upper(),))
        return encontrados[0] if encontrados else None

    def listar_pendentes_calibracao(self, hoje: Optional[date] = None) -> list[Equipamento]:
        """Equipamentos ativos vencidos, a vencer ou nunca calibrados (RN02/UC05).
        A regra de vencimento fica no domínio para não ser duplicada em SQL."""
        pendentes = [e for e in self._listar_onde("ativo = 1")
                     if e.situacao_calibracao(hoje) != Equipamento.SITUACAO_EM_DIA]
        return sorted(pendentes, key=lambda e: e.proxima_calibracao() or date.min)


class MedicaoDAO(DAOBase[Medicao]):
    """CRUD de medições. O SELECT usa JOIN para reconstruir, na mesma consulta,
    os objetos Equipamento e Tecnico associados a cada medição."""

    TABELA, CHAVE, CHAVE_SELECT = "medicoes", "id_medicao", "m.id_medicao"
    ORDENACAO = "m.data_medicao, e.codigo_tag, m.id_medicao"
    _COLUNAS_TECNICO = ("matricula", "nome", "setor", "perfil", "ativo")
    _COLUNAS_EQUIPAMENTO = ("codigo_tag", "descricao", "fabricante", "modelo",
                            "numero_serie", "resolucao", "unidade", "departamento",
                            "periodicidade_meses", "data_ultima_calibracao", "ativo")

    def __init__(self, conexao: ConexaoSQLite, tecnicos: Optional[TecnicoDAO] = None,
                 equipamentos: Optional[EquipamentoDAO] = None) -> None:
        super().__init__(conexao)
        self._tecnicos = tecnicos or TecnicoDAO(conexao)
        self._equipamentos = equipamentos or EquipamentoDAO(conexao)

    def _sql_select(self) -> str:
        colunas_t = ", ".join(f"t.{c} AS t_{c}" for c in self._COLUNAS_TECNICO)
        colunas_e = ", ".join(f"e.{c} AS e_{c}" for c in self._COLUNAS_EQUIPAMENTO)
        return (f"SELECT m.*, {colunas_t}, {colunas_e} FROM medicoes m "
                "INNER JOIN tecnicos t ON t.id_tecnico = m.id_tecnico "
                "INNER JOIN equipamentos e ON e.id_equipamento = m.id_equipamento")

    def _para_linha(self, medicao: Medicao) -> dict[str, Any]:
        if not medicao.equipamento.persistido or not medicao.tecnico.persistido:
            raise ErroValidacao("Equipamento e técnico precisam ser inseridos antes da medição.")
        return {"id_equipamento": medicao.equipamento.id, "id_tecnico": medicao.tecnico.id,
                "data_medicao": medicao.data_medicao, "parametro": medicao.parametro,
                "valor_nominal": medicao.valor_nominal,
                "tolerancia_inferior": medicao.tolerancia_inferior,
                "tolerancia_superior": medicao.tolerancia_superior,
                "valor_obtido": medicao.valor_obtido, "erro": medicao.erro,
                "status": medicao.status, "temperatura_c": medicao.temperatura_c,
                "observacao": medicao.observacao}

    def _para_objeto(self, linha: Mapping[str, Any]) -> Medicao:
        tecnico = self._tecnicos._para_objeto(
            {c: linha[f"t_{c}"] for c in self._COLUNAS_TECNICO} | {"id_tecnico": linha["id_tecnico"]})
        equipamento = self._equipamentos._para_objeto(
            {c: linha[f"e_{c}"] for c in self._COLUNAS_EQUIPAMENTO}
            | {"id_equipamento": linha["id_equipamento"]})
        medicao = Medicao(equipamento, tecnico, linha["parametro"],
                          Decimal(linha["valor_nominal"]),
                          Decimal(linha["tolerancia_inferior"]),
                          Decimal(linha["tolerancia_superior"]),
                          Decimal(linha["valor_obtido"]), Decimal(linha["temperatura_c"]),
                          linha["data_medicao"], linha["observacao"],
                          id_medicao=linha["id_medicao"])
        # Erro e status ficam gravados para os relatórios em SQL; ao ler, conferimos
        # que continuam iguais ao recálculo (detecta alteração feita fora do sistema).
        if linha["status"] != medicao.status or Decimal(linha["erro"]) != medicao.erro:
            raise ErroPersistencia(f"Medição {linha['id_medicao']}: erro/status gravados "
                                   "divergem do recálculo (dado alterado fora do sistema).")
        return medicao

    def listar_por_equipamento(self, id_equipamento: int) -> list[Medicao]:
        return self._listar_onde("m.id_equipamento = ?", (id_equipamento,))

    def inserir_lote(self, medicoes: list[Medicao]) -> list[int]:
        """Insere várias medições numa única transação: ou grava todas, ou nenhuma."""
        with self._db.transacao():
            return [self.inserir(medicao) for medicao in medicoes]


class RelatorioDAO:
    """Consultas relacionais (JOIN) usadas nos relatórios do terminal."""

    SQL_RELATORIO_CALIBRACAO = """
        SELECT e.codigo_tag, e.descricao, e.departamento, e.unidade,
               m.data_medicao, m.temperatura_c, t.nome AS tecnico, t.matricula,
               m.parametro, m.valor_nominal, m.tolerancia_inferior,
               m.tolerancia_superior, m.valor_obtido, m.erro, m.status
          FROM medicoes m
         INNER JOIN equipamentos e ON e.id_equipamento = m.id_equipamento
         INNER JOIN tecnicos     t ON t.id_tecnico     = m.id_tecnico
         ORDER BY e.codigo_tag, m.data_medicao, m.id_medicao"""

    SQL_PARECER_POR_ENSAIO = """
        SELECT e.codigo_tag, e.departamento, m.data_medicao, t.nome AS tecnico,
               COUNT(*)                                             AS pontos,
               SUM(m.status = 'REPROVADO')                          AS reprovados,
               MAX(ABS(CAST(m.erro AS REAL)))                       AS maior_erro_abs,
               CASE WHEN SUM(m.status = 'REPROVADO') > 0
                    THEN 'REPROVADO' ELSE 'APROVADO' END            AS parecer
          FROM medicoes m
         INNER JOIN equipamentos e ON e.id_equipamento = m.id_equipamento
         INNER JOIN tecnicos     t ON t.id_tecnico     = m.id_tecnico
         GROUP BY e.id_equipamento, m.data_medicao, t.id_tecnico
         ORDER BY m.data_medicao DESC, e.codigo_tag"""

    SQL_PRODUTIVIDADE_TECNICOS = """
        SELECT t.matricula, t.nome, t.perfil,
               COUNT(m.id_medicao)                      AS medicoes,
               COUNT(DISTINCT m.id_equipamento)         AS equipamentos,
               COALESCE(SUM(m.status = 'APROVADO'), 0)  AS aprovadas,
               COALESCE(SUM(m.status = 'REPROVADO'), 0) AS reprovadas
          FROM tecnicos t
          LEFT JOIN medicoes m ON m.id_tecnico = t.id_tecnico
         GROUP BY t.id_tecnico
         ORDER BY medicoes DESC, t.nome"""

    SQL_HISTORICO_EQUIPAMENTOS = """
        SELECT e.id_equipamento, e.codigo_tag, e.departamento,
               COUNT(m.id_medicao)  AS medicoes,
               MAX(m.data_medicao)  AS ultima_medicao
          FROM equipamentos e
          LEFT JOIN medicoes m ON m.id_equipamento = e.id_equipamento
         GROUP BY e.id_equipamento
         ORDER BY e.codigo_tag"""

    def __init__(self, conexao: ConexaoSQLite) -> None:
        self._db = conexao

    def _executar(self, sql: str) -> list[dict[str, Any]]:
        return [dict(linha) for linha in self._db.consultar(sql)]

    def relatorio_calibracao(self) -> list[dict[str, Any]]:
        return self._executar(self.SQL_RELATORIO_CALIBRACAO)

    def parecer_por_ensaio(self) -> list[dict[str, Any]]:
        return self._executar(self.SQL_PARECER_POR_ENSAIO)

    def produtividade_tecnicos(self) -> list[dict[str, Any]]:
        return self._executar(self.SQL_PRODUTIVIDADE_TECNICOS)

    def historico_equipamentos(self) -> list[dict[str, Any]]:
        return self._executar(self.SQL_HISTORICO_EQUIPAMENTOS)


# =============================================================================
# 5. CAMADA DE SERVIÇO
# =============================================================================
class ServicoCalibracao:
    """Aplica as regras que envolvem mais de uma entidade, de forma atômica."""

    def __init__(self, conexao: ConexaoSQLite, equipamentos: EquipamentoDAO,
                 medicoes: MedicaoDAO) -> None:
        self._db = conexao
        self._equipamentos = equipamentos
        self._medicoes = medicoes

    def registrar_ensaio(self, ensaio: EnsaioCalibracao) -> str:
        """Grava todas as medições do ensaio numa única transação.

        RN10: somente metrologista ativo registra medições.
        RN06: se algum ponto for reprovado, o equipamento não é liberado (a data
              de calibração não é atualizada); se todos forem aprovados, a data é
              atualizada e o próximo vencimento é recalculado (RN02).
        """
        if not ensaio.tecnico.pode_registrar_medicao():
            raise ErroRegraNegocio(f"RN10: {ensaio.tecnico.nome} ({ensaio.tecnico.perfil}) "
                                   "não pode registrar medições; exige metrologista ativo.")
        if not ensaio.equipamento.ativo:
            raise ErroRegraNegocio("Equipamento inativo não pode receber calibração.")
        if not ensaio.medicoes:
            raise ErroValidacao("O ensaio não possui pontos de medição.")
        equipamento = ensaio.equipamento
        with self._db.transacao():
            self._medicoes.inserir_lote(list(ensaio.medicoes))
            if ensaio.aprovado:
                data_anterior = equipamento.data_ultima_calibracao
                equipamento.registrar_calibracao(ensaio.data_medicao)

                def restaurar_data() -> None:
                    equipamento.data_ultima_calibracao = data_anterior

                self._db.ao_desfazer(restaurar_data)
                self._equipamentos.atualizar(equipamento)
        return ensaio.parecer
