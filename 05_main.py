"""
PROJETO APLICADO I - UniSENAI Florianópolis | Empresa parceira: Schulz S.A.
AV03 - Construção do MVP (Parte 1)

Arquivo: 05_main.py
Classe principal de demonstração: instancia os objetos de domínio, insere
registros de teste no SQLite, executa consultas relacionais com JOIN e exibe o
relatório de calibração no terminal.

Uso:
    python 05_main.py                    # recria calibracao_schulz.db ao lado do script
    python 05_main.py --banco :memory:   # executa tudo em memória, sem gerar arquivo
"""
from __future__ import annotations

import argparse
import importlib
import sys
import textwrap
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# O nome exigido pelo roteiro começa com dígito ("04_classes"), o que impede a
# sintaxe "import 04_classes". O importlib carrega o módulo normalmente.
nucleo = importlib.import_module("04_classes")

Tecnico = nucleo.Tecnico
Equipamento = nucleo.Equipamento
Medicao = nucleo.Medicao
EnsaioCalibracao = nucleo.EnsaioCalibracao


def formatar_data(valor: date | str | None) -> str:
    """Datas no padrão brasileiro (AV01: reformatar datas em localidade pt-BR)."""
    if valor is None:
        return "-"
    if isinstance(valor, str):
        valor = date.fromisoformat(valor)
    return valor.strftime("%d/%m/%Y")


class Console:
    """Funções de apresentação no terminal (sem nenhuma regra de negócio)."""

    LARGURA = 100

    @classmethod
    def titulo(cls, texto: str) -> None:
        print("\n" + "=" * cls.LARGURA)
        print(f" {texto}")
        print("=" * cls.LARGURA)

    @classmethod
    def secao(cls, texto: str) -> None:
        print(f"\n--- {texto} " + "-" * max(0, cls.LARGURA - len(texto) - 5))

    @staticmethod
    def campo(rotulo: str, valor: Any) -> None:
        print(f"  {rotulo:<30} {valor}")

    @staticmethod
    def sql(texto: str) -> None:
        for linha in textwrap.dedent(texto).strip().splitlines():
            print(f"  SQL> {linha}")

    @staticmethod
    def tabela(cabecalhos: Sequence[str], linhas: Iterable[Sequence[Any]],
               direita: Sequence[int] = ()) -> None:
        linhas = [[str(celula) for celula in linha] for linha in linhas]
        larguras = [max([len(c)] + [len(linha[i]) for linha in linhas])
                    for i, c in enumerate(cabecalhos)]

        def montar(celulas: Sequence[str]) -> str:
            return "  " + "  ".join(c.rjust(w) if i in direita else c.ljust(w)
                                    for i, (c, w) in enumerate(zip(celulas, larguras)))

        print(montar(cabecalhos))
        print("  " + "  ".join("-" * w for w in larguras))
        for linha in linhas:
            print(montar(linha))


class AplicacaoMVP:
    """Classe principal: conduz a demonstração do MVP em sete etapas."""

    def __init__(self, caminho_banco: str) -> None:
        self.caminho_banco = caminho_banco
        self.hoje = date.today()
        self.db = nucleo.ConexaoSQLite(caminho_banco)
        self.tecnicos = nucleo.TecnicoDAO(self.db)
        self.equipamentos = nucleo.EquipamentoDAO(self.db)
        self.medicoes = nucleo.MedicaoDAO(self.db, self.tecnicos, self.equipamentos)
        self.relatorios = nucleo.RelatorioDAO(self.db)
        self.servico = nucleo.ServicoCalibracao(self.db, self.equipamentos, self.medicoes)
        self.cenarios_ok = 0
        self.cenarios_total = 0

    # ------------------------------------------------------------------ fluxo
    def executar(self) -> int:
        print("#" * Console.LARGURA)
        print("#" + "SISTEMA DE CALIBRAÇÃO - SCHULZ S.A.".center(Console.LARGURA - 2) + "#")
        print("#" + "AV03 - MVP Parte 1 | POO em Python + SQLite (sqlite3)".center(
            Console.LARGURA - 2) + "#")
        print("#" * Console.LARGURA)
        print(f"  Data de execução: {formatar_data(self.hoje)}")

        self._remover_banco_anterior()
        with self.db:
            self.etapa_1_preparar_banco()
            self.etapa_2_instanciar_objetos()
            self.etapa_3_inserir_cadastros()
            self.etapa_4_registrar_ensaios()
            self.etapa_5_consultar_atualizar_excluir()
            self.etapa_6_validacoes_e_erros()
            self.etapa_7_relatorios_com_join()
            self.resumo_final()
        return 0 if self.cenarios_ok == self.cenarios_total else 1

    def _remover_banco_anterior(self) -> None:
        """Recria o arquivo a cada execução para a demonstração ser reprodutível."""
        if self.caminho_banco != ":memory:":
            Path(self.caminho_banco).unlink(missing_ok=True)

    # ------------------------------------------------------------- etapa 1
    def etapa_1_preparar_banco(self) -> None:
        Console.titulo("1. CONEXÃO E CRIAÇÃO DO ESQUEMA SQLITE")
        self.db.criar_esquema()
        Console.campo("Arquivo do banco", Path(self.db.caminho).name)
        Console.campo("Tabelas criadas", ", ".join(self.db.listar_tabelas()))
        Console.campo("PRAGMA foreign_keys",
                      "ON (integridade referencial ativa)" if self.db.chaves_estrangeiras_ativas()
                      else "OFF")

    # ------------------------------------------------------------- etapa 2
    def etapa_2_instanciar_objetos(self) -> None:
        Console.titulo("2. INSTANCIAÇÃO DOS OBJETOS DE DOMÍNIO (ANTES DE PERSISTIR)")
        h = self.hoje
        self.carla = Tecnico("17024-3", "Carla Mendes Ribeiro",
                             "Laboratório de Metrologia Dimensional")
        self.rafael = Tecnico("17110-8", "Rafael Antunes Weber",
                              "Laboratório de Metrologia Dimensional")
        self.helena = Tecnico("15530-1", "Helena Cristina Duarte", "Gestão da Qualidade",
                              Tecnico.PERFIL_SIGNATARIO)
        self.marcos = Tecnico("18002-5", "Marcos Vinícius Prado", "Auditoria Interna",
                              Tecnico.PERFIL_QUALIDADE)

        # Valores no formato das planilhas ("0,001") passam pelo saneamento da AV01.
        self.dispositivo = Equipamento(
            "703.1208", "Dispositivo de controle - furação do cabeçote", "Não consta",
            "0,001", "Usinagem I", periodicidade_meses=2,
            data_ultima_calibracao=h - timedelta(days=70))
        self.paquimetro = Equipamento(
            "PAQ-150-014", "Paquímetro digital 0-150 mm", "Mitutoyo", "0.01", "Fundição",
            periodicidade_meses=12, modelo="500-196-30", numero_serie="MT-882736",
            data_ultima_calibracao=h - timedelta(days=355))
        self.micrometro = Equipamento(
            "MIC-025-007", "Micrômetro externo digital 0-25 mm", "Mitutoyo", "0.001",
            "Compressores", periodicidade_meses=12, modelo="293-240-30",
            numero_serie="MT-0091823", data_ultima_calibracao=h - timedelta(days=485))
        self.relogio = Equipamento(
            "REL-010-003", "Relógio comparador 0-10 mm", "Mahr", "0.01", "Montagem",
            periodicidade_meses=6, modelo="Millimess 1003")

        print("  Técnicos (str() polimórfico, definido em cada subclasse de EntidadeBase):")
        for tecnico in (self.carla, self.rafael, self.helena, self.marcos):
            print(f"    - {tecnico}   persistido={tecnico.persistido}")
        print("\n  Equipamentos e situação de calibração calculada pelo domínio:")
        Console.tabela(
            ["TAG", "RESOLUÇÃO", "PERIOD.", "ÚLT. CALIBRAÇÃO", "PRÓXIMA", "SITUAÇÃO"],
            [[e.codigo_tag, f"{e.resolucao} {e.unidade}", f"{e.periodicidade_meses} m",
              formatar_data(e.data_ultima_calibracao), formatar_data(e.proxima_calibracao()),
              e.situacao_calibracao(h)]
             for e in (self.dispositivo, self.paquimetro, self.micrometro, self.relogio)])

    # ------------------------------------------------------------- etapa 3
    def etapa_3_inserir_cadastros(self) -> None:
        Console.titulo("3. INSERT - CADASTRO DE TÉCNICOS E EQUIPAMENTOS")
        linhas = []
        for tecnico in (self.carla, self.rafael, self.helena, self.marcos):
            self.tecnicos.inserir(tecnico)
            linhas.append(["tecnicos", tecnico.id, tecnico.resumo()])
        for equipamento in (self.dispositivo, self.paquimetro, self.micrometro, self.relogio):
            self.equipamentos.inserir(equipamento)
            linhas.append(["equipamentos", equipamento.id, equipamento.resumo()])
        Console.tabela(["TABELA", "ID GERADO", "REGISTRO"], linhas, direita=[1])

    # ------------------------------------------------------------- etapa 4
    def etapa_4_registrar_ensaios(self) -> None:
        Console.titulo("4. INSERT - ENSAIOS DE CALIBRAÇÃO (CLASSE MEDICAO)")
        h = self.hoje

        ensaio_mic = EnsaioCalibracao(self.micrometro, self.rafael, h - timedelta(days=120), "20,1")
        ensaio_mic.adicionar_ponto("1P_BLOCO 5 MM", "5.000", "-0.002", "0.002", "5.001")
        ensaio_mic.adicionar_ponto("2P_BLOCO 15 MM", "15.000", "-0.002", "0.002", "15.0015")
        ensaio_mic.adicionar_ponto("3P_BLOCO 25 MM", "25.000", "-0.002", "0.002", "24.999")

        # Pontos e valores no formato do relatório da MMC analisado na AV01.
        ensaio_disp = EnsaioCalibracao(self.dispositivo, self.carla, h, "20,4°")
        ensaio_disp.adicionar_ponto("62P_DIÂMETRO 1", "6.0800", "-0.0100", "0.0100", "6,0787295")
        ensaio_disp.adicionar_ponto("106P_DIÂMETRO 1", "12.0000", "-0.0150", "0.0150", "12.0094")
        ensaio_disp.adicionar_ponto("13P_POSIÇÃO 1", "0.0000", "0", "0.0500", "0.0213")
        ensaio_disp.adicionar_ponto("PLANICIDADE_REF", "0.0000", "0", "0.0200", "0.0068")

        ensaio_paq = EnsaioCalibracao(self.paquimetro, self.carla, h - timedelta(days=1), "19,8")
        ensaio_paq.adicionar_ponto("1P_BLOCO 25 MM", "25.00", "-0.02", "0.02", "25.01")
        ensaio_paq.adicionar_ponto("2P_BLOCO 50 MM", "50.00", "-0.02", "0.02", "50.02",
                                   "Valor exatamente no limite superior (limite incluso).")
        ensaio_paq.adicionar_ponto("3P_BLOCO 100 MM", "100.00", "-0.03", "0.03", "100.04",
                                   "Desvio acima da tolerância: encaminhar para ajuste.")
        self.ensaio_dispositivo = ensaio_disp

        for ensaio in (ensaio_mic, ensaio_disp, ensaio_paq):
            equipamento = ensaio.equipamento
            Console.secao(f"Ensaio {equipamento.codigo_tag} em {formatar_data(ensaio.data_medicao)}"
                          f" por {ensaio.tecnico.nome}")
            parecer = self.servico.registrar_ensaio(ensaio)
            Console.tabela(
                ["ID", "PARÂMETRO", "FAIXA ACEITA", "OBTIDO", "ERRO", "STATUS"],
                [[m.id, m.parametro, f"[{m.limite_inferior} ; {m.limite_superior}]",
                  m.valor_obtido, f"{m.erro:+}", m.status] for m in ensaio.medicoes],
                direita=[0, 3, 4])
            Console.campo("Parecer do ensaio (RN06)", f"{parecer} - "
                          f"{len(ensaio.medicoes) - len(ensaio.pontos_reprovados)}/"
                          f"{len(ensaio.medicoes)} pontos conformes")
            if ensaio.aprovado:
                Console.campo("Efeito no equipamento", "liberado; próxima calibração em "
                              f"{formatar_data(equipamento.proxima_calibracao())}")
            else:
                Console.campo("Efeito no equipamento", "NÃO liberado; data de calibração mantida "
                              f"({formatar_data(equipamento.data_ultima_calibracao)})")
        print("\n  Observação: o parâmetro '62P_DIÂMETRO 1' foi gravado como "
              f"'{ensaio_disp.medicoes[0].parametro}' e o valor '6,0787295' como "
              f"{ensaio_disp.medicoes[0].valor_obtido} (regras de saneamento da AV01).")

    # ------------------------------------------------------------- etapa 5
    def etapa_5_consultar_atualizar_excluir(self) -> None:
        Console.titulo("5. SELECT, UPDATE E DELETE (LENDO DE VOLTA DO BANCO)")

        Console.secao("5.1 SELECT por TAG - objeto novo, reconstruído a partir do banco")
        relido = self.equipamentos.buscar_por_tag("703.1208")
        Console.campo("Objeto relido", repr(relido))
        Console.campo("Última calibração (gravada)", formatar_data(relido.data_ultima_calibracao))
        Console.campo("Próxima calibração", formatar_data(relido.proxima_calibracao()))
        Console.campo("Situação", relido.situacao_calibracao(self.hoje))

        Console.secao("5.2 SELECT com JOIN no DAO - medições do paquímetro e seus objetos associados")
        medicoes = self.medicoes.listar_por_equipamento(self.paquimetro.id)
        Console.tabela(
            ["ID", "PARÂMETRO", "TOL. INF", "TOL. SUP", "OBTIDO", "STATUS", "TÉCNICO (objeto)"],
            [[m.id, m.parametro, f"{m.tolerancia_inferior:+}", f"{m.tolerancia_superior:+}",
              m.valor_obtido, m.status, m.tecnico.nome] for m in medicoes],
            direita=[0, 2, 3, 4])
        print("  Tolerâncias e status foram persistidos e conferidos com o recálculo na leitura.")

        Console.secao("5.3 UPDATE - técnico muda de setor")
        antes = self.rafael.setor
        self.rafael.setor = "Laboratório de Metrologia - Turno B"
        self.tecnicos.atualizar(self.rafael)
        Console.campo("Setor anterior", antes)
        Console.campo("Setor relido do banco", self.tecnicos.obter(self.rafael.id).setor)

        Console.secao("5.4 UPDATE - equipamento muda de periodicidade")
        self.relogio.periodicidade_meses = 3
        self.relogio.numero_serie = "MH-112984"
        self.equipamentos.atualizar(self.relogio)
        relido = self.equipamentos.obter(self.relogio.id)
        Console.campo("Periodicidade relida", f"{relido.periodicidade_meses} meses")
        Console.campo("Número de série relido", relido.numero_serie)

        Console.secao("5.5 DELETE - cadastro feito por engano")
        temporario = Tecnico("19001-2", "Lucas Teixeira Moura", "Estágio", Tecnico.PERFIL_QUALIDADE)
        id_temporario = self.tecnicos.inserir(temporario)
        self.tecnicos.excluir(id_temporario)
        Console.campo("Técnico temporário", f"ID {id_temporario} inserido e depois excluído")
        Console.campo(f"buscar_por_id({id_temporario})", self.tecnicos.buscar_por_id(id_temporario))

        Console.secao("5.6 SELECT filtrado - metrologistas ativos")
        for tecnico in self.tecnicos.listar_por_perfil(Tecnico.PERFIL_METROLOGISTA):
            print(f"    - {tecnico} | {tecnico.setor}")

    # ------------------------------------------------------------- etapa 6
    def _cenario(self, descricao: str, acao: Callable[[], Any],
                 excecao_esperada: type[Exception]) -> None:
        self.cenarios_total += 1
        try:
            acao()
        except excecao_esperada as erro:
            self.cenarios_ok += 1
            print(f"  [OK]    {descricao}")
            print(f"          {type(erro).__name__}: {erro}")
        else:
            print(f"  [FALHA] {descricao}: nenhuma exceção foi lançada.")

    def etapa_6_validacoes_e_erros(self) -> None:
        Console.titulo("6. VALIDAÇÕES DE DOMÍNIO E TRATAMENTO DE ERROS SQL")
        h = self.hoje

        Console.secao("6.1 Validações no domínio (o objeto inválido nem chega a existir)")
        self._cenario("Matrícula fora do padrão 99999-9",
                      lambda: Tecnico("ABC-1", "Pedro Alves", "Metrologia"), nucleo.ErroValidacao)

        def renomear_invalido() -> None:
            self.carla.nome = "X"

        self._cenario("Encapsulamento: setter recusa nome inválido em objeto já criado",
                      renomear_invalido, nucleo.ErroValidacao)
        print(f"          nome continua '{self.carla.nome}'")
        self._cenario("Tolerância inferior maior que a superior",
                      lambda: Medicao(self.dispositivo, self.carla, "1P_TESTE", "10", "0.01",
                                      "-0.01", "10", "20"), nucleo.ErroValidacao)
        self._cenario("Temperatura ambiente fora de 15-30 °C ('35,0°')",
                      lambda: EnsaioCalibracao(self.relogio, self.carla, h, "35,0°")
                      .adicionar_ponto("1P_CURSO 1 MM", "1", "-0.01", "0.01", "1"),
                      nucleo.ErroValidacao)
        self._cenario("Data de medição no futuro",
                      lambda: Medicao(self.relogio, self.carla, "1P_CURSO 1 MM", "1", "-0.01",
                                      "0.01", "1", "20", h + timedelta(days=1)),
                      nucleo.ErroValidacao)

        def signatario_registra() -> None:
            ensaio = EnsaioCalibracao(self.relogio, self.helena, h, "20,0")
            ensaio.adicionar_ponto("1P_CURSO 1 MM", "1.00", "-0.01", "0.01", "1.00")
            self.servico.registrar_ensaio(ensaio)

        self._cenario("RN10: signatário tentando registrar medição", signatario_registra,
                      nucleo.ErroRegraNegocio)

        Console.secao("6.2 Restrições do banco traduzidas em exceções do domínio")
        self._cenario("UNIQUE: matrícula já cadastrada",
                      lambda: self.tecnicos.inserir(
                          Tecnico("17024-3", "Outra Pessoa Silva", "Metrologia")),
                      nucleo.ErroRegistroDuplicado)
        self._cenario("FOREIGN KEY (RESTRICT): excluir equipamento que possui medições",
                      lambda: self.equipamentos.excluir(self.dispositivo.id),
                      nucleo.ErroIntegridadeReferencial)

        def medicao_sem_equipamento() -> None:
            fantasma = Equipamento("FANTASMA-01", "Equipamento inexistente", "Não consta",
                                   "0.01", "Teste", id_equipamento=999)
            self.medicoes.inserir(Medicao(fantasma, self.carla, "1P_TESTE", "1", "-0.1",
                                          "0.1", "1", "20"))

        self._cenario("FOREIGN KEY: medição apontando para equipamento inexistente (ID 999)",
                      medicao_sem_equipamento, nucleo.ErroIntegridadeReferencial)
        self._cenario("CHECK: SQL direto tentando gravar status 'TALVEZ'",
                      lambda: self.db.executar("UPDATE medicoes SET status = ? WHERE id_medicao = ?",
                                               ("TALVEZ", 1)),
                      nucleo.ErroPersistencia)
        self._cenario("DELETE de ID inexistente",
                      lambda: self.tecnicos.excluir(9999), nucleo.ErroRegistroNaoEncontrado)

        Console.secao("6.3 Transação atômica (ROLLBACK) e integridade na leitura")
        total_antes = self.medicoes.contar()
        repeticao = EnsaioCalibracao(self.dispositivo, self.carla, h, "20,4")
        ponto_novo = repeticao.adicionar_ponto("200P_RAIO 1", "3.0000", "-0.0100", "0.0100", "3.0021")
        repeticao.adicionar_ponto("62P_DIÂMETRO 1", "6.0800", "-0.0100", "0.0100", "6.0790")
        self._cenario("Lote com 2 pontos em que o 2º repete equipamento+data+parâmetro (AV01)",
                      lambda: self.servico.registrar_ensaio(repeticao),
                      nucleo.ErroRegistroDuplicado)
        print(f"          medições no banco: antes={total_antes} depois={self.medicoes.contar()}"
              f" | ID do 1º ponto após o ROLLBACK: {ponto_novo.id}")

        alvo = self.ensaio_dispositivo.medicoes[0]
        original = str(alvo.valor_obtido)
        self.db.executar("UPDATE medicoes SET valor_obtido = ? WHERE id_medicao = ?",
                         ("99.999", alvo.id))
        try:
            self._cenario("Valor alterado por fora do sistema é detectado ao ler",
                          lambda: self.medicoes.buscar_por_id(alvo.id), nucleo.ErroPersistencia)
        finally:
            self.db.executar("UPDATE medicoes SET valor_obtido = ? WHERE id_medicao = ?",
                             (original, alvo.id))
        print(f"          valor original restaurado: {self.medicoes.obter(alvo.id).valor_obtido}")

    # ------------------------------------------------------------- etapa 7
    def etapa_7_relatorios_com_join(self) -> None:
        Console.titulo("7. RELATÓRIOS COM CONSULTAS RELACIONAIS (JOIN)")

        Console.secao("7.1 RELATÓRIO DE CALIBRAÇÃO - medicoes x equipamentos x tecnicos")
        Console.sql(nucleo.RelatorioDAO.SQL_RELATORIO_CALIBRACAO)
        grupos: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for linha in self.relatorios.relatorio_calibracao():
            grupos.setdefault((linha["codigo_tag"], linha["data_medicao"]), []).append(linha)
        for (tag, data_medicao), pontos in grupos.items():
            cabecalho = pontos[0]
            reprovados = sum(p["status"] == Medicao.STATUS_REPROVADO for p in pontos)
            print("\n  " + "-" * 96)
            print(f"  EQUIPAMENTO {tag} - {cabecalho['descricao']}")
            print(f"  Departamento: {cabecalho['departamento']:<22} Data: {formatar_data(data_medicao)}"
                  f"   Temperatura: {cabecalho['temperatura_c']} °C")
            print(f"  Executado por: {cabecalho['tecnico']} (matrícula {cabecalho['matricula']})"
                  f"   Unidade: {cabecalho['unidade']}")
            print("  " + "-" * 96)
            Console.tabela(
                ["PARÂMETRO", "NOMINAL", "TOL. INF", "TOL. SUP", "OBTIDO", "ERRO", "STATUS"],
                [[p["parametro"], p["valor_nominal"], self._sinal(p["tolerancia_inferior"]),
                  self._sinal(p["tolerancia_superior"]), p["valor_obtido"],
                  self._sinal(p["erro"]), p["status"]] for p in pontos],
                direita=[1, 2, 3, 4, 5])
            parecer = Medicao.STATUS_REPROVADO if reprovados else Medicao.STATUS_APROVADO
            print(f"  PARECER DO ENSAIO: {parecer} ({len(pontos) - reprovados}/{len(pontos)} "
                  "pontos dentro da tolerância)")

        Console.secao("7.2 Parecer consolidado por ensaio - JOIN + GROUP BY")
        Console.sql(nucleo.RelatorioDAO.SQL_PARECER_POR_ENSAIO)
        Console.tabela(
            ["TAG", "DEPARTAMENTO", "DATA", "TÉCNICO", "PONTOS", "REPROV.", "MAIOR |ERRO|", "PARECER"],
            [[r["codigo_tag"], r["departamento"], formatar_data(r["data_medicao"]), r["tecnico"],
              r["pontos"], r["reprovados"], f"{r['maior_erro_abs']:.7f}".rstrip("0").rstrip("."),
              r["parecer"]] for r in self.relatorios.parecer_por_ensaio()],
            direita=[4, 5, 6])

        Console.secao("7.3 Produção por técnico - LEFT JOIN (inclui quem não mediu)")
        Console.sql(nucleo.RelatorioDAO.SQL_PRODUTIVIDADE_TECNICOS)
        Console.tabela(
            ["MATRÍCULA", "NOME", "PERFIL", "MEDIÇÕES", "EQUIP.", "APROV.", "REPROV."],
            [[r["matricula"], r["nome"], r["perfil"], r["medicoes"], r["equipamentos"],
              r["aprovadas"], r["reprovadas"]] for r in self.relatorios.produtividade_tecnicos()],
            direita=[3, 4, 5, 6])

        Console.secao("7.4 Situação de calibração e alertas (LEFT JOIN + regra RN02 do domínio)")
        Console.sql(nucleo.RelatorioDAO.SQL_HISTORICO_EQUIPAMENTOS)
        equipamentos = {e.id: e for e in self.equipamentos.listar()}
        Console.tabela(
            ["TAG", "DEPARTAMENTO", "MEDIÇÕES", "ÚLT. MEDIÇÃO", "PRÓX. CALIBRAÇÃO", "SITUAÇÃO"],
            [[r["codigo_tag"], r["departamento"], r["medicoes"], formatar_data(r["ultima_medicao"]),
              formatar_data(equipamentos[r["id_equipamento"]].proxima_calibracao()),
              equipamentos[r["id_equipamento"]].situacao_calibracao(self.hoje)]
             for r in self.relatorios.historico_equipamentos()],
            direita=[2])
        print()
        for equipamento in self.equipamentos.listar_pendentes_calibracao(self.hoje):
            dias = equipamento.dias_para_vencimento(self.hoje)
            prazo = "nunca calibrado" if dias is None else (
                f"vence em {dias} dia(s)" if dias >= 0 else f"vencido há {-dias} dia(s)")
            print(f"  [ALERTA] {equipamento.codigo_tag} ({equipamento.departamento}): "
                  f"{equipamento.situacao_calibracao(self.hoje)} - {prazo}")

    @staticmethod
    def _sinal(valor: str) -> str:
        """Exibe tolerâncias e erros com sinal explícito (zero fica sem sinal)."""
        return valor if valor.startswith("-") or Decimal(valor) == 0 else f"+{valor}"

    # ------------------------------------------------------------- resumo
    def resumo_final(self) -> None:
        Console.titulo("RESUMO DA EXECUÇÃO")
        Console.campo("Técnicos cadastrados", self.tecnicos.contar())
        Console.campo("Equipamentos cadastrados", self.equipamentos.contar())
        Console.campo("Medições gravadas", self.medicoes.contar())
        Console.campo("Cenários de erro tratados", f"{self.cenarios_ok}/{self.cenarios_total}")
        Console.campo("Banco de dados", Path(self.db.caminho).name)
        situacao = "CONCLUÍDA COM SUCESSO" if self.cenarios_ok == self.cenarios_total else "COM FALHAS"
        print(f"\n  Demonstração {situacao}.")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Demonstração do MVP (AV03 - Parte 1).")
    parser.add_argument("--banco", default=str(Path(__file__).with_name("calibracao_schulz.db")),
                        help="arquivo SQLite a ser (re)criado, ou :memory:")
    argumentos = parser.parse_args()
    try:
        return AplicacaoMVP(argumentos.banco).executar()
    except nucleo.ErroSistema as erro:
        print(f"\n  [ERRO] {type(erro).__name__}: {erro}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
