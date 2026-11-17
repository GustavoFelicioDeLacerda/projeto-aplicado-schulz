"""
Testes automatizados do MVP (AV03 - Parte 1).

Executar a partir da raiz do repositório:
    python -m unittest discover -s tests -v
"""
import contextlib
import importlib
import io
import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
nucleo = importlib.import_module("04_classes")
principal = importlib.import_module("05_main")

HOJE = date.today()


def novo_tecnico(matricula="17024-3", perfil="METROLOGISTA"):
    return nucleo.Tecnico(matricula, "Carla Mendes Ribeiro", "Metrologia", perfil)


def novo_equipamento(tag="PAQ-150-014", ultima=None):
    return nucleo.Equipamento(tag, "Paquímetro digital 0-150 mm", "Mitutoyo", "0.01",
                              "Fundição", 12, data_ultima_calibracao=ultima)


def nova_medicao(obtido="25.01", equipamento=None, tecnico=None, parametro="1P_BLOCO 25 MM"):
    return nucleo.Medicao(equipamento or novo_equipamento(), tecnico or novo_tecnico(),
                          parametro, "25.00", "-0.02", "0.02", obtido, "20,4°")


class TestSaneamento(unittest.TestCase):
    """Regras de ETL herdadas da AV01 (seção 3.1)."""

    def test_decimal_no_formato_das_planilhas(self):
        self.assertEqual(nucleo.para_decimal("20,4°", "t"), Decimal("20.4"))
        self.assertEqual(nucleo.para_decimal("6,0787295", "v"), Decimal("6.0787295"))
        self.assertEqual(nucleo.para_decimal(0.1, "v"), Decimal("0.1"))

    def test_decimal_invalido(self):
        for valor in ("abc", "", True, float("nan")):
            with self.assertRaises(nucleo.ErroValidacao):
                nucleo.para_decimal(valor, "v")

    def test_sentinelas_viram_nulo(self):
        for sentinela in ("------", "00/00/0000", "  ", "Não informado"):
            self.assertIsNone(nucleo.limpar_texto(sentinela, "c", obrigatorio=False))
        self.assertEqual(nucleo.limpar_texto("  Usinagem   I ", "c"), "Usinagem I")

    def test_normalizacao_de_parametro(self):
        self.assertEqual(nucleo.normalizar_parametro("62P_DIÂMETRO 1"), "62P_DIAMETRO_1")
        self.assertEqual(nucleo.normalizar_parametro("PLANICIDADE_REF"), "REF_PLANICIDADE")
        self.assertEqual(nucleo.normalizar_parametro("entre centros_ref"), "REF_ENTRE_CENTROS")

    def test_soma_de_meses_no_fim_do_mes(self):
        self.assertEqual(nucleo.somar_meses(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(nucleo.somar_meses(date(2026, 11, 3), 2), date(2027, 1, 3))


class TestMedicao(unittest.TestCase):
    """Lógica de validação do status APROVADO/REPROVADO (RN05 da AV01)."""

    def test_erro_por_soma_algebrica(self):
        self.assertEqual(nova_medicao("24.99").erro, Decimal("-0.01"))

    def test_dentro_da_tolerancia_aprovado(self):
        self.assertEqual(nova_medicao("25.01").status, "APROVADO")

    def test_limites_sao_inclusivos(self):
        self.assertEqual(nova_medicao("25.02").status, "APROVADO")
        self.assertEqual(nova_medicao("24.98").status, "APROVADO")

    def test_fora_da_tolerancia_reprovado(self):
        self.assertEqual(nova_medicao("25.0201").status, "REPROVADO")
        self.assertEqual(nova_medicao("24.9799").status, "REPROVADO")

    def test_tolerancia_assimetrica(self):
        medicao = nucleo.Medicao(novo_equipamento(), novo_tecnico(), "13P_POSICAO 1",
                                 "0", "0", "0.05", "-0.001", "20")
        self.assertEqual(medicao.status, "REPROVADO")

    def test_status_recalculado_quando_o_valor_muda(self):
        medicao = nova_medicao("25.01")
        medicao.valor_obtido = "25.05"
        self.assertEqual(medicao.status, "REPROVADO")

    def test_tolerancia_invertida_e_rejeitada(self):
        with self.assertRaises(nucleo.ErroValidacao):
            nucleo.Medicao(novo_equipamento(), novo_tecnico(), "1P_X", "1", "0.1", "-0.1", "1", "20")

    def test_temperatura_e_data_validadas(self):
        medicao = nova_medicao()
        with self.assertRaises(nucleo.ErroValidacao):
            medicao.temperatura_c = "35"
        with self.assertRaises(nucleo.ErroValidacao):
            medicao.data_medicao = HOJE + timedelta(days=1)

    def test_parecer_do_ensaio_reprovado_se_um_ponto_falhar(self):
        ensaio = nucleo.EnsaioCalibracao(novo_equipamento(), novo_tecnico(), HOJE, "20")
        ensaio.adicionar_ponto("1P_A", "10", "-0.01", "0.01", "10.005")
        ensaio.adicionar_ponto("2P_B", "10", "-0.01", "0.01", "10.02")
        self.assertEqual(ensaio.parecer, "REPROVADO")
        self.assertEqual(len(ensaio.pontos_reprovados), 1)


class TestEncapsulamento(unittest.TestCase):

    def test_setter_valida_depois_da_criacao(self):
        tecnico = novo_tecnico()
        with self.assertRaises(nucleo.ErroValidacao):
            tecnico.matricula = "ABC"
        self.assertEqual(tecnico.matricula, "17024-3")

    def test_id_e_imutavel(self):
        tecnico = novo_tecnico()
        tecnico.atribuir_id(1)
        with self.assertRaises(nucleo.ErroValidacao):
            tecnico.atribuir_id(2)

    def test_rn10_somente_metrologista_ativo(self):
        self.assertFalse(novo_tecnico(perfil="SIGNATARIO").pode_registrar_medicao())
        tecnico = novo_tecnico()
        tecnico.ativo = False
        self.assertFalse(tecnico.pode_registrar_medicao())

    def test_situacao_de_calibracao(self):
        self.assertEqual(novo_equipamento().situacao_calibracao(), "SEM CALIBRACAO")
        self.assertEqual(novo_equipamento(ultima=HOJE).situacao_calibracao(), "EM DIA")
        self.assertEqual(novo_equipamento(ultima=HOJE - timedelta(days=400)).situacao_calibracao(),
                         "VENCIDA")


class TestPersistenciaSQLite(unittest.TestCase):
    """CRUD real em banco SQLite em memória."""

    def setUp(self):
        self.db = nucleo.ConexaoSQLite(":memory:")
        self.db.criar_esquema()
        self.tecnicos = nucleo.TecnicoDAO(self.db)
        self.equipamentos = nucleo.EquipamentoDAO(self.db)
        self.medicoes = nucleo.MedicaoDAO(self.db, self.tecnicos, self.equipamentos)
        self.servico = nucleo.ServicoCalibracao(self.db, self.equipamentos, self.medicoes)
        self.tecnico = novo_tecnico()
        self.equipamento = novo_equipamento(ultima=HOJE - timedelta(days=355))
        self.tecnicos.inserir(self.tecnico)
        self.equipamentos.inserir(self.equipamento)

    def tearDown(self):
        self.db.fechar()

    def test_chaves_estrangeiras_ativas(self):
        self.assertTrue(self.db.chaves_estrangeiras_ativas())

    def test_ida_e_volta_preserva_decimais_tolerancia_e_status(self):
        medicao = nucleo.Medicao(self.equipamento, self.tecnico, "62P_DIÂMETRO 1", "6.0800",
                                 "-0.0100", "0.0100", "6,0787295", "20,4°")
        self.medicoes.inserir(medicao)
        relida = self.medicoes.obter(medicao.id)
        self.assertEqual(relida.valor_obtido, Decimal("6.0787295"))
        self.assertEqual(relida.tolerancia_inferior, Decimal("-0.0100"))
        self.assertEqual(relida.status, medicao.status)
        self.assertEqual(relida.equipamento.codigo_tag, "PAQ-150-014")
        self.assertEqual(relida.tecnico.nome, "Carla Mendes Ribeiro")

    def test_update_e_delete(self):
        self.tecnico.setor = "Turno B"
        self.tecnicos.atualizar(self.tecnico)
        self.assertEqual(self.tecnicos.obter(self.tecnico.id).setor, "Turno B")
        extra = novo_tecnico("19001-2")
        self.tecnicos.inserir(extra)
        self.tecnicos.excluir(extra.id)
        self.assertIsNone(self.tecnicos.buscar_por_id(extra.id))

    def test_unique_vira_erro_de_duplicidade(self):
        with self.assertRaises(nucleo.ErroRegistroDuplicado):
            self.tecnicos.inserir(novo_tecnico())

    def test_fk_restrict_bloqueia_exclusao(self):
        self.medicoes.inserir(nova_medicao(equipamento=self.equipamento, tecnico=self.tecnico))
        with self.assertRaises(nucleo.ErroIntegridadeReferencial):
            self.equipamentos.excluir(self.equipamento.id)

    def test_registro_inexistente(self):
        with self.assertRaises(nucleo.ErroRegistroNaoEncontrado):
            self.tecnicos.excluir(999)

    def test_lote_e_atomico(self):
        primeira = nova_medicao(equipamento=self.equipamento, tecnico=self.tecnico)
        repetida = nova_medicao(equipamento=self.equipamento, tecnico=self.tecnico)
        with self.assertRaises(nucleo.ErroRegistroDuplicado):
            self.medicoes.inserir_lote([primeira, repetida])
        self.assertEqual(self.medicoes.contar(), 0)
        self.assertIsNone(primeira.id)

    def test_check_do_banco(self):
        with self.assertRaises(nucleo.ErroPersistencia):
            self.db.executar("UPDATE tecnicos SET perfil = 'GERENTE'")

    def test_servico_atualiza_data_somente_se_aprovado(self):
        data_original = self.equipamento.data_ultima_calibracao
        reprovado = nucleo.EnsaioCalibracao(self.equipamento, self.tecnico, HOJE, "20")
        reprovado.adicionar_ponto("1P_A", "10", "-0.01", "0.01", "10.5")
        self.assertEqual(self.servico.registrar_ensaio(reprovado), "REPROVADO")
        self.assertEqual(self.equipamentos.obter(self.equipamento.id).data_ultima_calibracao,
                         data_original)
        aprovado = nucleo.EnsaioCalibracao(self.equipamento, self.tecnico, HOJE, "20")
        aprovado.adicionar_ponto("2P_B", "10", "-0.01", "0.01", "10.001")
        self.assertEqual(self.servico.registrar_ensaio(aprovado), "APROVADO")
        self.assertEqual(self.equipamentos.obter(self.equipamento.id).data_ultima_calibracao, HOJE)

    def test_rn10_bloqueia_signatario(self):
        signatario = novo_tecnico("15530-1", "SIGNATARIO")
        self.tecnicos.inserir(signatario)
        ensaio = nucleo.EnsaioCalibracao(self.equipamento, signatario, HOJE, "20")
        ensaio.adicionar_ponto("1P_A", "10", "-0.01", "0.01", "10")
        with self.assertRaises(nucleo.ErroRegraNegocio):
            self.servico.registrar_ensaio(ensaio)
        self.assertEqual(self.medicoes.contar(), 0)


class TestDemonstracao(unittest.TestCase):
    """Executa o 05_main.py inteiro em memória e confere o resultado."""

    def test_fluxo_completo(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = principal.AplicacaoMVP(":memory:").executar()
        texto = saida.getvalue()
        self.assertEqual(codigo, 0)
        self.assertRegex(texto, r"Cenários de erro tratados\s+13/13")
        self.assertIn("PARECER DO ENSAIO: REPROVADO", texto)
        self.assertIn("Demonstração CONCLUÍDA COM SUCESSO", texto)


if __name__ == "__main__":
    unittest.main()
