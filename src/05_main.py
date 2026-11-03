"""AV03 - MVP Parte 1: Classe principal e demonstracao de fluxo."""

import sys
from datetime import date, timedelta
from decimal import Decimal

from mysql.connector import Error as MySQLError

from classes import (Conexao, Tecnico, Equipamento, Medicao,
                     TecnicoDAO, EquipamentoDAO, MedicaoDAO,
                     ErroValidacao, ErroPersistencia)

LARGURA = 78


def titulo(texto):
    print("\n" + "=" * LARGURA)
    print(f"  {texto}")
    print("=" * LARGURA)


def subtitulo(texto):
    print(f"\n--- {texto} " + "-" * (LARGURA - len(texto) - 5))


def linha(campos):
    for k, v in campos.items():
        print(f"  {k:<24} {v}")


class SistemaCalibracao:
    def __init__(self):
        self.db = Conexao()
        self.tecnicos = TecnicoDAO(self.db)
        self.equipamentos = EquipamentoDAO(self.db)
        self.medicoes = MedicaoDAO(self.db)

    def testar_conexao(self):
        titulo("1. TESTE DE CONEXAO COM O BANCO DE DADOS")
        try:
            cur = self.db.cursor()
            cur.execute("SELECT VERSION(), DATABASE(), NOW()")
            row = cur.fetchone()
            cur.close()
            linha({"Servidor MySQL": row["VERSION()"],
                   "Banco de dados": row["DATABASE()"],
                   "Data/hora servidor": row["NOW()"]})
            print("\n  [OK] Conexao estabelecida com sucesso.")
            return True
        except ErroPersistencia as e:
            print(f"\n  [FALHA] {e}")
            print("\n  Verifique se o MySQL esta rodando e se o banco")
            print("  'bd_certificados_schulz' foi criado (setup_av03.sql).")
            return False

    def demonstrar_crud(self):
        titulo("2. DEMONSTRACAO DE OPERACOES CRUD")

        subtitulo("2.1 INSERT - Novo tecnico metrologista")
        try:
            novo = Tecnico(nome="Ana Paula Ferreira",
                           email="ana.ferreira@schulz.com.br",
                           senha_hash="$2y$12$demoAV03",
                           papel="METROLOGISTA",
                           registro_profissional="TEC-MET-9901/SC")
            id_tec = self.tecnicos.inserir(novo)
            linha({"ID gerado": id_tec, "Nome": novo.nome,
                   "Papel": novo.papel, "Status": "Inserido"})
        except (ErroValidacao, ErroPersistencia) as e:
            print(f"  [ERRO] {e}")

        subtitulo("2.2 INSERT - Novo equipamento")
        try:
            eq = Equipamento(tag="MIC-EXT-099",
                             descricao="Micrometro Externo Digital 0-25mm",
                             tipo="Micrometro", fabricante="Mitutoyo",
                             modelo="293-240-30", numero_serie="MT-9911001",
                             resolucao_mm=Decimal("0.00100"),
                             data_calibracao_prevista=date.today() + timedelta(days=365),
                             id_cliente=1)
            id_eq = self.equipamentos.inserir(eq)
            linha({"ID gerado": id_eq, "Tag": eq.tag,
                   "Cliente (FK)": eq.id_cliente, "Status": "Inserido"})
        except (ErroValidacao, ErroPersistencia) as e:
            print(f"  [ERRO] {e}")

        subtitulo("2.3 INSERT - Nova medicao com validacao de tolerancia")
        try:
            m = Medicao(ponto_medicao="P1 - Diametro Externo (AV03)",
                        valor_nominal=Decimal("12.0000"),
                        valor_medido=Decimal("12.0035"),
                        repetitividade=Decimal("0.00015"),
                        incerteza=Decimal("0.00120"),
                        tolerancia=Decimal("0.0100"))
            id_med = self.medicoes.inserir(m)
            linha({"ID gerado": id_med, "Ponto": m.ponto_medicao,
                   "Erro calculado": f"{m.erro_encontrado} mm",
                   "Tolerancia": f"+-{m.tolerancia} mm",
                   "Parecer": m.classificar()})
        except (ErroValidacao, ErroPersistencia) as e:
            print(f"  [ERRO] {e}")

        subtitulo("2.4 SELECT - Listagem de tecnicos ativos")
        try:
            lista = self.tecnicos.listar(apenas_ativos=True)
            print(f"  Total encontrado: {len(lista)}\n")
            print(f"  {'ID':<5} {'NOME':<32} {'PAPEL':<14} {'REGISTRO':<16}")
            print(f"  {'-'*5} {'-'*32} {'-'*14} {'-'*16}")
            for t in lista[:8]:
                print(f"  {t.id_usuario:<5} {t.nome[:32]:<32} "
                      f"{t.papel:<14} {(t.registro_profissional or '-')[:16]:<16}")
        except ErroPersistencia as e:
            print(f"  [ERRO] {e}")

        subtitulo("2.5 UPDATE - Alteracao de dados")
        try:
            if 'id_tec' in locals():
                t = self.tecnicos.buscar_por_id(id_tec)
                if t:
                    t.nome = "Ana Paula Ferreira Lima"
                    ok = self.tecnicos.atualizar(t)
                    linha({"ID": t.id_usuario, "Novo nome": t.nome,
                           "Status": "Atualizado" if ok else "Nao encontrado"})
        except (ErroValidacao, ErroPersistencia) as e:
            print(f"  [ERRO] {e}")

        subtitulo("2.6 DELETE - Remocao controlada")
        try:
            if 'id_med' in locals():
                ok = self.medicoes.excluir(id_med)
                linha({"ID removido": id_med,
                       "Status": "Excluido" if ok else "Nao encontrado"})
        except ErroPersistencia as e:
            print(f"  [ERRO] {e}")

    def demonstrar_validacoes(self):
        titulo("3. VALIDACAO DE REGRAS DE NEGOCIO")

        subtitulo("3.1 RN06 - Signatario sem registro profissional")
        try:
            Tecnico(nome="Teste Invalido", email="teste@schulz.com.br",
                    senha_hash="hash", papel="SIGNATARIO",
                    registro_profissional=None)
            print("  [FALHA] Deveria ter lancado excecao.")
        except ErroValidacao as e:
            print(f"  [OK] Excecao capturada: {e}")

        subtitulo("3.2 E-mail com formato invalido")
        try:
            Tecnico(nome="Teste Email", email="email-sem-arroba",
                    senha_hash="hash", papel="METROLOGISTA")
            print("  [FALHA] Deveria ter lancado excecao.")
        except ErroValidacao as e:
            print(f"  [OK] Excecao capturada: {e}")

        subtitulo("3.3 RN05 - Calculo automatico do erro (soma algebrica)")
        m1 = Medicao("Teste A", Decimal("10.0000"), Decimal("10.0003"),
                     Decimal("0.00008"), Decimal("0.00045"))
        m2 = Medicao("Teste B", Decimal("10.0000"), Decimal("9.9995"),
                     Decimal("0.00008"), Decimal("0.00045"))
        print(f"  Medicao A: nominal=10.0000 medido=10.0003 -> erro={m1.erro_encontrado} ({m1.classificar()})")
        print(f"  Medicao B: nominal=10.0000 medido=9.9995  -> erro={m2.erro_encontrado} ({m2.classificar()})")

        subtitulo("3.4 Validacao de tolerancia - ponto fora do limite")
        m3 = Medicao("Teste C", Decimal("20.0000"), Decimal("20.0250"),
                     Decimal("0.00200"), Decimal("0.01200"),
                     tolerancia=Decimal("0.0100"))
        print(f"  Erro={m3.erro_encontrado} | Tolerancia=+-{m3.tolerancia} | Parecer={m3.classificar()}")
        if not m3.dentro_da_tolerancia():
            print("  [OK] Ponto corretamente reprovado pela tolerancia.")

    def relatorio_certificados(self):
        titulo("4. RELATORIO 1 - CERTIFICADOS COM INSTRUMENTO E MEDICOES")
        sql = """SELECT c.numero, c.status, c.resultado, c.data_emissao,
                        i.tag, i.tipo, cl.razao_social,
                        COUNT(cm.id_medicao) AS total_medicoes
                 FROM certificado c
                 INNER JOIN instrumento i ON i.id_instrumento = c.id_instrumento
                 INNER JOIN cliente cl ON cl.id_cliente = i.id_cliente
                 LEFT JOIN certificado_medicao cm ON cm.id_certificado = c.id_certificado
                 GROUP BY c.id_certificado, c.numero, c.status, c.resultado,
                          c.data_emissao, i.tag, i.tipo, cl.razao_social
                 ORDER BY c.data_emissao DESC"""
        try:
            cur = self.db.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            print(f"  Total de certificados: {len(rows)}\n")
            print(f"  {'NUMERO':<12} {'TAG':<14} {'STATUS':<20} {'RESULTADO':<24} {'MED':<4}")
            print(f"  {'-'*12} {'-'*14} {'-'*20} {'-'*24} {'-'*4}")
            for r in rows:
                print(f"  {r['numero']:<12} {r['tag']:<14} {r['status']:<20} "
                      f"{r['resultado']:<24} {r['total_medicoes']:<4}")
        except MySQLError as e:
            print(f"  [ERRO] {e.msg}")

    def relatorio_pendentes(self):
        titulo("5. RELATORIO 2 - CERTIFICADOS PENDENTES E APROVADOS")
        sql = """SELECT c.numero, c.status, c.resultado,
                        u.nome AS metrologista, s.nome AS signatario
                 FROM certificado c
                 INNER JOIN usuario u ON u.id_usuario = c.id_metrologista
                 LEFT JOIN usuario s ON s.id_usuario = c.id_signatario
                 WHERE c.status IN ('PENDENTE_APROVACAO', 'APROVADO')
                 ORDER BY c.status, c.numero"""
        try:
            cur = self.db.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            pend = [r for r in rows if r["status"] == "PENDENTE_APROVACAO"]
            apro = [r for r in rows if r["status"] == "APROVADO"]
            print(f"  Pendentes de aprovacao: {len(pend)}")
            print(f"  Aprovados: {len(apro)}\n")
            print(f"  {'NUMERO':<12} {'STATUS':<22} {'METROLOGISTA':<28} {'SIGNATARIO':<24}")
            print(f"  {'-'*12} {'-'*22} {'-'*28} {'-'*24}")
            for r in rows:
                print(f"  {r['numero']:<12} {r['status']:<22} "
                      f"{r['metrologista'][:28]:<28} "
                      f"{(r['signatario'] or '(pendente)')[:24]:<24}")
        except MySQLError as e:
            print(f"  [ERRO] {e.msg}")

    def relatorio_rastreabilidade(self):
        titulo("6. RELATORIO 3 - RASTREABILIDADE: MEDICOES E PADROES")
        sql = """SELECT m.ponto_medicao, m.valor_nominal, m.valor_medido,
                        m.erro_encontrado, p.codigo_identificacao AS padrao,
                        p.certificado_rastreabilidade AS laudo_rbc,
                        p.validade AS validade_padrao, mp.lote_utilizacao
                 FROM medicao m
                 INNER JOIN medicao_padrao mp ON mp.id_medicao = m.id_medicao
                 INNER JOIN padrao_calibracao p ON p.id_padrao = mp.id_padrao
                 ORDER BY m.id_medicao, p.codigo_identificacao"""
        try:
            cur = self.db.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            print(f"  Total de vinculos medicao-padrao: {len(rows)}\n")
            print(f"  {'PONTO DE MEDICAO':<34} {'PADRAO':<14} {'ERRO':<12} {'VALIDADE':<12}")
            print(f"  {'-'*34} {'-'*14} {'-'*12} {'-'*12}")
            for r in rows:
                print(f"  {r['ponto_medicao'][:34]:<34} {r['padrao']:<14} "
                      f"{str(r['erro_encontrado']):<12} {str(r['validade_padrao']):<12}")
        except MySQLError as e:
            print(f"  [ERRO] {e.msg}")

    def relatorio_alertas(self):
        titulo("7. ALERTAS - CALIBRACOES VENCIDAS (RN03)")
        try:
            venc = self.equipamentos.listar_calibracoes_vencidas()
            if not venc:
                print("  Nenhum equipamento com calibracao vencida.")
                return
            print(f"  Total de equipamentos vencidos: {len(venc)}\n")
            for e in venc:
                print(f"  {e.tag:<16} {e.tipo:<16} venceu em "
                      f"{e.data_calibracao_prevista} ({abs(e.dias_para_vencer())} dias)")
        except ErroPersistencia as e:
            print(f"  [ERRO] {e}")

    def executar(self):
        print("\n" + "#" * LARGURA)
        print("#" + " " * (LARGURA - 2) + "#")
        print("#" + "  SISTEMA DE CERTIFICADOS DE CALIBRACAO - SCHULZ S.A.".center(LARGURA - 2) + "#")
        print("#" + "  AV03 - MVP Parte 1 | POO + Persistencia MySQL".center(LARGURA - 2) + "#")
        print("#" + " " * (LARGURA - 2) + "#")
        print("#" * LARGURA)
        if not self.testar_conexao():
            print("\n  Execucao interrompida.")
            return
        self.demonstrar_crud()
        self.demonstrar_validacoes()
        self.relatorio_certificados()
        self.relatorio_pendentes()
        self.relatorio_rastreabilidade()
        self.relatorio_alertas()
        titulo("EXECUCAO CONCLUIDA COM SUCESSO")
        print("  Todos os modulos foram executados sem erros fatais.\n")

    def encerrar(self):
        self.db.fechar()


def main():
    sistema = None
    try:
        sistema = SistemaCalibracao()
        sistema.executar()
    except KeyboardInterrupt:
        print("\n\n  Execucao interrompida pelo usuario.")
    except ErroPersistencia as e:
        print(f"\n  [ERRO DE PERSISTENCIA] {e}")
    except Exception as e:
        print(f"\n  [ERRO INESPERADO] {type(e).__name__}: {e}")
    finally:
        if sistema:
            sistema.encerrar()
        sys.exit(0)


if __name__ == "__main__":
    main()
