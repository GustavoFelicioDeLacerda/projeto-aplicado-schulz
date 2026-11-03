# Automação da Emissão de Certificados de Calibração

Projeto Aplicado I — UniSENAI Florianópolis
Empresa parceira: **Schulz S.A.**

## Sobre o projeto

Sistema para automatizar a emissão de certificados de calibração metrológica, eliminando as três digitações manuais hoje existentes entre as planilhas de medição da MMC e o certificado final.

## Equipe

- Gabriel Oliveira Born
- Gustavo Felicio de Lacerda
- Iduilton Junior de Souza Santos
- Mateus Foltran Tomaz
- Mateus Paterno

Orientador: Prof. MSc. Hugo Menezes Barra

## Entregas

| Entrega | Conteúdo | Pasta |
|---|---|---|
| AV01 | Identificação do problema, requisitos e regras de negócio | `docs/` |
| AV02 | Modelagem do banco de dados relacional | `docs/` |
| AV03 | MVP Parte 1 — POO e persistência | `src/` |

## Tecnologias

- Python 3.10+
- MySQL 8.0
- mysql-connector-python

## Como executar

1. `pip install mysql-connector-python`
2. Execute `sql/setup_av03.sql` no MySQL Workbench
3. Ajuste `CONFIG_PADRAO` em `src/classes.py` com suas credenciais
4. `cd src` e `python 05_main.py`

## Nota sobre nomenclatura

O roteiro sugere `04_classes.py`. Python não importa módulos que iniciam com dígito, então o arquivo foi renomeado para `classes.py`.
