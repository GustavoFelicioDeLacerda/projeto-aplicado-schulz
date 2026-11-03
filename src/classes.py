"""AV03 - MVP Parte 1: Classes de dominio e persistencia (MySQL)."""

import re
from datetime import date
from decimal import Decimal
from typing import Optional, List, Dict, Any

import mysql.connector
from mysql.connector import Error as MySQLError


class ErroValidacao(Exception):
    pass


class ErroPersistencia(Exception):
    pass


class Conexao:
    _instancia = None

    CONFIG_PADRAO = {
        "host": "localhost",
        "port": 3306,
        "user": "root",
        "password": "",
        "database": "bd_certificados_schulz",
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
        "autocommit": False,
    }

    def __new__(cls, config=None):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._config = config or cls.CONFIG_PADRAO
            cls._instancia._conn = None
        return cls._instancia

    def conectar(self):
        try:
            if self._conn is None or not self._conn.is_connected():
                self._conn = mysql.connector.connect(**self._config)
            return self._conn
        except MySQLError as e:
            raise ErroPersistencia(f"Falha ao conectar ao MySQL: {e}") from e

    def cursor(self, dictionary=True):
        return self.conectar().cursor(dictionary=dictionary)

    def commit(self):
        self.conectar().commit()

    def rollback(self):
        if self._conn and self._conn.is_connected():
            self._conn.rollback()

    def fechar(self):
        if self._conn and self._conn.is_connected():
            self._conn.close()
            self._conn = None


class Tecnico:
    PAPEIS_VALIDOS = {"METROLOGISTA", "SIGNATARIO", "QUALIDADE"}

    def __init__(self, nome, email, senha_hash, papel,
                 registro_profissional=None, ativo=True, id_usuario=None):
        self.id_usuario = id_usuario
        self.nome = nome
        self.email = email
        self.senha_hash = senha_hash
        self.papel = papel
        self.registro_profissional = registro_profissional
        self.ativo = ativo
        self._validar()

    def _validar(self):
        if not self.nome or len(self.nome.strip()) < 3:
            raise ErroValidacao("Nome deve ter ao menos 3 caracteres.")
        if not re.match(r"^[\w\.\-]+@[\w\.\-]+\.\w{2,}$", self.email or ""):
            raise ErroValidacao(f"E-mail invalido: {self.email}")
        if self.papel not in self.PAPEIS_VALIDOS:
            raise ErroValidacao(f"Papel invalido: {self.papel}")
        if self.papel == "SIGNATARIO" and not self.registro_profissional:
            raise ErroValidacao("Signatario exige registro profissional (RN06).")

    def __repr__(self):
        return f"<Tecnico id={self.id_usuario} nome='{self.nome}' papel={self.papel}>"


class Equipamento:
    def __init__(self, tag, descricao, tipo, fabricante, modelo, numero_serie,
                 resolucao_mm, data_calibracao_prevista, id_cliente,
                 id_instrumento=None):
        self.id_instrumento = id_instrumento
        self.tag = tag
        self.descricao = descricao
        self.tipo = tipo
        self.fabricante = fabricante
        self.modelo = modelo
        self.numero_serie = numero_serie
        self.resolucao_mm = Decimal(str(resolucao_mm))
        self.data_calibracao_prevista = data_calibracao_prevista
        self.id_cliente = id_cliente
        self._validar()

    def _validar(self):
        if not self.tag or len(self.tag.strip()) < 3:
            raise ErroValidacao("Tag deve ter ao menos 3 caracteres.")
        if self.resolucao_mm <= 0:
            raise ErroValidacao("Resolucao deve ser maior que zero.")
        if not isinstance(self.data_calibracao_prevista, date):
            raise ErroValidacao("Data de calibracao invalida.")
        if not self.id_cliente or self.id_cliente <= 0:
            raise ErroValidacao("Equipamento exige cliente valido (FK).")

    def calibracao_vencida(self):
        return self.data_calibracao_prevista < date.today()

    def dias_para_vencer(self):
        return (self.data_calibracao_prevista - date.today()).days

    def __repr__(self):
        return f"<Equipamento id={self.id_instrumento} tag='{self.tag}'>"


class Medicao:
    def __init__(self, ponto_medicao, valor_nominal, valor_medido,
                 repetitividade, incerteza, tolerancia=Decimal("0.0100"),
                 id_medicao=None):
        self.id_medicao = id_medicao
        self.ponto_medicao = ponto_medicao
        self.valor_nominal = Decimal(str(valor_nominal))
        self.valor_medido = Decimal(str(valor_medido))
        self.repetitividade = Decimal(str(repetitividade))
        self.incerteza = Decimal(str(incerteza))
        self.tolerancia = Decimal(str(tolerancia))
        self.erro_encontrado = self._calcular_erro()
        self._validar()

    def _calcular_erro(self):
        return (self.valor_medido - self.valor_nominal).quantize(Decimal("0.0001"))

    def _validar(self):
        if not self.ponto_medicao or len(self.ponto_medicao.strip()) < 2:
            raise ErroValidacao("Ponto de medicao deve ser identificado.")
        if self.valor_medido < 0:
            raise ErroValidacao("Valor medido nao pode ser negativo.")
        if self.repetitividade < 0:
            raise ErroValidacao("Repetitividade nao pode ser negativa.")
        if self.incerteza < 0:
            raise ErroValidacao("Incerteza nao pode ser negativa.")

    def dentro_da_tolerancia(self):
        return abs(self.erro_encontrado) <= self.tolerancia

    def classificar(self):
        if not self.dentro_da_tolerancia():
            return "REJEITADO"
        if abs(self.erro_encontrado) > (self.tolerancia * Decimal("0.8")):
            return "APROVADO_COM_RESTRICAO"
        return "APROVADO"

    def __repr__(self):
        return f"<Medicao id={self.id_medicao} erro={self.erro_encontrado}>"


class TecnicoDAO:
    def __init__(self, conexao=None):
        self.db = conexao or Conexao()

    def inserir(self, t):
        sql = """INSERT INTO usuario
                 (nome, email, senha_hash, papel, registro_profissional, ativo)
                 VALUES (%s, %s, %s, %s, %s, %s)"""
        try:
            cur = self.db.cursor()
            cur.execute(sql, (t.nome, t.email, t.senha_hash, t.papel,
                              t.registro_profissional, 1 if t.ativo else 0))
            self.db.commit()
            t.id_usuario = cur.lastrowid
            cur.close()
            return t.id_usuario
        except MySQLError as e:
            self.db.rollback()
            if e.errno == 1062:
                raise ErroPersistencia(f"E-mail ja cadastrado: {t.email}") from e
            raise ErroPersistencia(f"Erro ao inserir tecnico: {e.msg}") from e

    def buscar_por_id(self, id_usuario):
        try:
            cur = self.db.cursor()
            cur.execute("SELECT * FROM usuario WHERE id_usuario = %s", (id_usuario,))
            row = cur.fetchone()
            cur.close()
            return self._row(row) if row else None
        except MySQLError as e:
            raise ErroPersistencia(f"Erro na consulta: {e.msg}") from e

    def listar(self, apenas_ativos=True):
        sql = "SELECT * FROM usuario"
        if apenas_ativos:
            sql += " WHERE ativo = 1"
        sql += " ORDER BY nome"
        try:
            cur = self.db.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            return [self._row(r) for r in rows]
        except MySQLError as e:
            raise ErroPersistencia(f"Erro na listagem: {e.msg}") from e

    def atualizar(self, t):
        if not t.id_usuario:
            raise ErroValidacao("Tecnico sem ID.")
        sql = """UPDATE usuario SET nome=%s, email=%s, papel=%s,
                 registro_profissional=%s, ativo=%s WHERE id_usuario=%s"""
        try:
            cur = self.db.cursor()
            cur.execute(sql, (t.nome, t.email, t.papel, t.registro_profissional,
                              1 if t.ativo else 0, t.id_usuario))
            self.db.commit()
            n = cur.rowcount
            cur.close()
            return n > 0
        except MySQLError as e:
            self.db.rollback()
            raise ErroPersistencia(f"Erro ao atualizar: {e.msg}") from e

    def excluir(self, id_usuario):
        try:
            cur = self.db.cursor()
            cur.execute("DELETE FROM usuario WHERE id_usuario = %s", (id_usuario,))
            self.db.commit()
            n = cur.rowcount
            cur.close()
            return n > 0
        except MySQLError as e:
            self.db.rollback()
            if e.errno == 1451:
                raise ErroPersistencia("Tecnico possui certificados vinculados.") from e
            raise ErroPersistencia(f"Erro ao excluir: {e.msg}") from e

    @staticmethod
    def _row(r):
        return Tecnico(id_usuario=r["id_usuario"], nome=r["nome"], email=r["email"],
                       senha_hash=r["senha_hash"], papel=r["papel"],
                       registro_profissional=r.get("registro_profissional"),
                       ativo=bool(r["ativo"]))


class EquipamentoDAO:
    def __init__(self, conexao=None):
        self.db = conexao or Conexao()

    def inserir(self, e):
        sql = """INSERT INTO instrumento
                 (tag, descricao, tipo, fabricante, modelo, numero_serie,
                  resolucao_mm, data_calibracao_prevista, id_cliente)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        try:
            cur = self.db.cursor()
            cur.execute(sql, (e.tag, e.descricao, e.tipo, e.fabricante, e.modelo,
                              e.numero_serie, e.resolucao_mm,
                              e.data_calibracao_prevista, e.id_cliente))
            self.db.commit()
            e.id_instrumento = cur.lastrowid
            cur.close()
            return e.id_instrumento
        except MySQLError as err:
            self.db.rollback()
            if err.errno == 1062:
                raise ErroPersistencia(f"Tag ja cadastrada: {e.tag}") from err
            if err.errno == 1452:
                raise ErroPersistencia(f"Cliente inexistente (id={e.id_cliente}).") from err
            raise ErroPersistencia(f"Erro ao inserir equipamento: {err.msg}") from err

    def buscar_por_id(self, id_instrumento):
        try:
            cur = self.db.cursor()
            cur.execute("SELECT * FROM instrumento WHERE id_instrumento = %s",
                        (id_instrumento,))
            row = cur.fetchone()
            cur.close()
            return self._row(row) if row else None
        except MySQLError as e:
            raise ErroPersistencia(f"Erro na consulta: {e.msg}") from e

    def listar(self):
        try:
            cur = self.db.cursor()
            cur.execute("SELECT * FROM instrumento ORDER BY tag")
            rows = cur.fetchall()
            cur.close()
            return [self._row(r) for r in rows]
        except MySQLError as e:
            raise ErroPersistencia(f"Erro na listagem: {e.msg}") from e

    def listar_calibracoes_vencidas(self):
        sql = """SELECT * FROM instrumento
                 WHERE data_calibracao_prevista < CURDATE()
                 ORDER BY data_calibracao_prevista"""
        try:
            cur = self.db.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            return [self._row(r) for r in rows]
        except MySQLError as e:
            raise ErroPersistencia(f"Erro na consulta: {e.msg}") from e

    def atualizar(self, e):
        if not e.id_instrumento:
            raise ErroValidacao("Equipamento sem ID.")
        sql = """UPDATE instrumento SET descricao=%s, tipo=%s, fabricante=%s,
                 modelo=%s, numero_serie=%s, resolucao_mm=%s,
                 data_calibracao_prevista=%s, id_cliente=%s
                 WHERE id_instrumento=%s"""
        try:
            cur = self.db.cursor()
            cur.execute(sql, (e.descricao, e.tipo, e.fabricante, e.modelo,
                              e.numero_serie, e.resolucao_mm,
                              e.data_calibracao_prevista, e.id_cliente,
                              e.id_instrumento))
            self.db.commit()
            n = cur.rowcount
            cur.close()
            return n > 0
        except MySQLError as err:
            self.db.rollback()
            raise ErroPersistencia(f"Erro ao atualizar: {err.msg}") from err

    def excluir(self, id_instrumento):
        try:
            cur = self.db.cursor()
            cur.execute("DELETE FROM instrumento WHERE id_instrumento = %s",
                        (id_instrumento,))
            self.db.commit()
            n = cur.rowcount
            cur.close()
            return n > 0
        except MySQLError as err:
            self.db.rollback()
            if err.errno == 1451:
                raise ErroPersistencia("Equipamento possui certificados vinculados.") from err
            raise ErroPersistencia(f"Erro ao excluir: {err.msg}") from err

    @staticmethod
    def _row(r):
        return Equipamento(id_instrumento=r["id_instrumento"], tag=r["tag"],
                           descricao=r["descricao"], tipo=r["tipo"],
                           fabricante=r["fabricante"], modelo=r["modelo"],
                           numero_serie=r["numero_serie"],
                           resolucao_mm=r["resolucao_mm"],
                           data_calibracao_prevista=r["data_calibracao_prevista"],
                           id_cliente=r["id_cliente"])


class MedicaoDAO:
    def __init__(self, conexao=None):
        self.db = conexao or Conexao()

    def inserir(self, m):
        sql = """INSERT INTO medicao
                 (ponto_medicao, valor_nominal, valor_medido,
                  erro_encontrado, repetitividade, incerteza)
                 VALUES (%s, %s, %s, %s, %s, %s)"""
        try:
            cur = self.db.cursor()
            cur.execute(sql, (m.ponto_medicao, m.valor_nominal, m.valor_medido,
                              m.erro_encontrado, m.repetitividade, m.incerteza))
            self.db.commit()
            m.id_medicao = cur.lastrowid
            cur.close()
            return m.id_medicao
        except MySQLError as e:
            self.db.rollback()
            raise ErroPersistencia(f"Erro ao inserir medicao: {e.msg}") from e

    def buscar_por_id(self, id_medicao):
        try:
            cur = self.db.cursor()
            cur.execute("SELECT * FROM medicao WHERE id_medicao = %s", (id_medicao,))
            row = cur.fetchone()
            cur.close()
            return self._row(row) if row else None
        except MySQLError as e:
            raise ErroPersistencia(f"Erro na consulta: {e.msg}") from e

    def listar(self):
        try:
            cur = self.db.cursor()
            cur.execute("SELECT * FROM medicao ORDER BY id_medicao")
            rows = cur.fetchall()
            cur.close()
            return [self._row(r) for r in rows]
        except MySQLError as e:
            raise ErroPersistencia(f"Erro na listagem: {e.msg}") from e

    def listar_por_certificado(self, id_certificado):
        sql = """SELECT m.* FROM medicao m
                 INNER JOIN certificado_medicao cm ON cm.id_medicao = m.id_medicao
                 WHERE cm.id_certificado = %s
                 ORDER BY cm.ordem_apresentacao"""
        try:
            cur = self.db.cursor()
            cur.execute(sql, (id_certificado,))
            rows = cur.fetchall()
            cur.close()
            return [self._row(r) for r in rows]
        except MySQLError as e:
            raise ErroPersistencia(f"Erro na consulta: {e.msg}") from e

    def atualizar(self, m):
        if not m.id_medicao:
            raise ErroValidacao("Medicao sem ID.")
        sql = """UPDATE medicao SET ponto_medicao=%s, valor_nominal=%s,
                 valor_medido=%s, erro_encontrado=%s, repetitividade=%s,
                 incerteza=%s WHERE id_medicao=%s"""
        try:
            cur = self.db.cursor()
            cur.execute(sql, (m.ponto_medicao, m.valor_nominal, m.valor_medido,
                              m.erro_encontrado, m.repetitividade, m.incerteza,
                              m.id_medicao))
            self.db.commit()
            n = cur.rowcount
            cur.close()
            return n > 0
        except MySQLError as e:
            self.db.rollback()
            raise ErroPersistencia(f"Erro ao atualizar: {e.msg}") from e

    def excluir(self, id_medicao):
        try:
            cur = self.db.cursor()
            cur.execute("DELETE FROM medicao WHERE id_medicao = %s", (id_medicao,))
            self.db.commit()
            n = cur.rowcount
            cur.close()
            return n > 0
        except MySQLError as e:
            self.db.rollback()
            if e.errno == 1451:
                raise ErroPersistencia("Medicao associada a certificados.") from e
            raise ErroPersistencia(f"Erro ao excluir: {e.msg}") from e

    @staticmethod
    def _row(r):
        return Medicao(id_medicao=r["id_medicao"],
                       ponto_medicao=r["ponto_medicao"],
                       valor_nominal=r["valor_nominal"],
                       valor_medido=r["valor_medido"],
                       repetitividade=r["repetitividade"],
                       incerteza=r["incerteza"])
