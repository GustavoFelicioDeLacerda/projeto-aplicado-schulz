# Automação da Emissão de Certificados de Calibração — Schulz S.A.

Projeto Aplicado I — UniSENAI Florianópolis · Empresa parceira: **Schulz S.A.**

Sistema para automatizar o registro de calibrações metrológicas e a emissão de certificados,
eliminando as três digitações manuais hoje feitas entre o relatório da MMC, as planilhas de registro e o
certificado final.

## Equipe

- Gabriel Oliveira Born
- Gustavo Felicio de Lacerda
- Iduilton Junior de Souza Santos
- Mateus Foltran Tomaz
- Mateus Paterno

Docentes: Prof. MSc. Hugo Menezes Barra e Prof. Rodrigo Losina

## Entregas

| Entrega | Conteúdo | Onde |
|---|---|---|
| AV01 | Identificação do problema, requisitos e regras de negócio | `docs/AV01_PA1_Tema01_Requisitos.pdf` |
| AV02 | Modelagem do banco de dados relacional | `docs/AV02_PA1_Tema02_Modelagem_BD.pdf` |
| AV03 | MVP Parte 1: classes POO em Python e persistência em SQLite | `04_classes.py`, `05_main.py`, `06_mvp_parte1.md`, `docs/AV03_MVP_Parte1.pdf` |

## Como executar (AV03)

Requisito: Python 3.10 ou superior. Não há dependências externas (o `sqlite3` faz parte do Python).

```bash
python 05_main.py
```

O script recria o banco `calibracao_schulz.db` ao lado dele e percorre sete etapas: conexão, instanciação
dos objetos, `INSERT`, ensaios de calibração, `SELECT`/`UPDATE`/`DELETE`, cenários de erro e relatórios com
`JOIN`. Para rodar sem gerar arquivo: `python 05_main.py --banco :memory:`.

Testes automatizados:

```bash
python -m unittest discover -s tests -v
```

## Estrutura

```text
04_classes.py      Classes de domínio (Tecnico, Equipamento, Medicao), conexão SQLite e DAOs (CRUD)
05_main.py         Classe principal de demonstração (relatório de calibração no terminal)
06_mvp_parte1.md   Documentação técnica: POO, UML, tratamento de erros SQL e validação do fluxo
tests/             Testes automatizados (unittest)
docs/              PDFs das entregas
```

O nome `04_classes.py` segue o roteiro. Como nomes iniciados por dígito não podem ser usados em
`import`, o módulo é carregado com `importlib.import_module("04_classes")`.
