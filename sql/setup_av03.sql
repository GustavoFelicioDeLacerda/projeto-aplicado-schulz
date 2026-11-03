-- =====================================================================
-- PROJETO APLICADO I - UniSENAI Florianopolis
-- AV03 - MVP Parte 1 | Script de Setup do Banco de Dados
-- Cliente: Schulz S.A.
-- =====================================================================

DROP DATABASE IF EXISTS bd_certificados_schulz;
CREATE DATABASE bd_certificados_schulz
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE bd_certificados_schulz;

CREATE TABLE cliente (
    id_cliente INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    razao_social VARCHAR(150) NOT NULL,
    cnpj VARCHAR(18) NOT NULL UNIQUE,
    contato VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL,
    telefone VARCHAR(20) NOT NULL,
    endereco VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE usuario (
    id_usuario INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    senha_hash VARCHAR(255) NOT NULL,
    papel ENUM('METROLOGISTA','SIGNATARIO','QUALIDADE') NOT NULL,
    registro_profissional VARCHAR(30) NULL,
    ativo TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE instrumento (
    id_instrumento INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tag VARCHAR(30) NOT NULL UNIQUE,
    descricao VARCHAR(150) NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    fabricante VARCHAR(80) NOT NULL,
    modelo VARCHAR(80) NOT NULL,
    numero_serie VARCHAR(50) NOT NULL,
    resolucao_mm DECIMAL(8,5) NOT NULL,
    data_calibracao_prevista DATE NOT NULL,
    id_cliente INT UNSIGNED NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_instrumento_cliente FOREIGN KEY (id_cliente)
        REFERENCES cliente (id_cliente) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE INDEX idx_instr_tag ON instrumento(tag);
CREATE INDEX idx_instr_calib_prevista ON instrumento(data_calibracao_prevista);

CREATE TABLE padrao_calibracao (
    id_padrao INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    codigo_identificacao VARCHAR(40) NOT NULL UNIQUE,
    descricao VARCHAR(150) NOT NULL,
    certificado_rastreabilidade VARCHAR(60) NOT NULL,
    validade DATE NOT NULL,
    incerteza_padrao DECIMAL(8,5) NOT NULL,
    orgao_calibrador VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_padrao_incerteza CHECK (incerteza_padrao >= 0)
) ENGINE=InnoDB;

CREATE INDEX idx_padrao_validade ON padrao_calibracao(validade);

CREATE TABLE certificado (
    id_certificado INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    numero VARCHAR(10) NOT NULL UNIQUE,
    id_instrumento INT UNSIGNED NOT NULL,
    id_metrologista INT UNSIGNED NOT NULL,
    id_signatario INT UNSIGNED NULL,
    data_emissao DATE NOT NULL,
    data_aprovacao DATETIME NULL,
    temperatura_c DECIMAL(4,2) NOT NULL,
    umidade_relativa_pct DECIMAL(4,2) NOT NULL,
    incerteza_total DECIMAL(8,5) NOT NULL,
    resultado ENUM('APROVADO','APROVADO_COM_RESTRICAO','REJEITADO') NOT NULL,
    status ENUM('RASCUNHO','PENDENTE_APROVACAO','APROVADO','CANCELADO') NOT NULL DEFAULT 'RASCUNHO',
    observacoes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cert_instrumento FOREIGN KEY (id_instrumento)
        REFERENCES instrumento (id_instrumento) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_cert_metrologista FOREIGN KEY (id_metrologista)
        REFERENCES usuario (id_usuario) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_cert_signatario FOREIGN KEY (id_signatario)
        REFERENCES usuario (id_usuario) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_cert_numero_formato CHECK (numero REGEXP '^[0-9]{5}/[0-9]{4}$'),
    CONSTRAINT chk_cert_temperatura CHECK (temperatura_c BETWEEN 15.00 AND 30.00),
    CONSTRAINT chk_cert_umidade CHECK (umidade_relativa_pct BETWEEN 20.00 AND 80.00)
) ENGINE=InnoDB;

CREATE INDEX idx_cert_numero ON certificado(numero);
CREATE INDEX idx_cert_data_emissao ON certificado(data_emissao);
CREATE INDEX idx_cert_status ON certificado(status);

CREATE TABLE medicao (
    id_medicao INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ponto_medicao VARCHAR(50) NOT NULL,
    valor_nominal DECIMAL(10,4) NOT NULL,
    valor_medido DECIMAL(10,4) NOT NULL,
    erro_encontrado DECIMAL(10,4) NOT NULL,
    repetitividade DECIMAL(8,5) NOT NULL,
    incerteza DECIMAL(8,5) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_medicao_valor_medido CHECK (valor_medido >= 0),
    CONSTRAINT chk_medicao_repetitividade CHECK (repetitividade >= 0),
    CONSTRAINT chk_medicao_incerteza CHECK (incerteza >= 0)
) ENGINE=InnoDB;

CREATE TABLE certificado_medicao (
    id_certificado INT UNSIGNED NOT NULL,
    id_medicao INT UNSIGNED NOT NULL,
    ordem_apresentacao INT UNSIGNED NOT NULL,
    PRIMARY KEY (id_certificado, id_medicao),
    CONSTRAINT fk_cm_certificado FOREIGN KEY (id_certificado)
        REFERENCES certificado (id_certificado) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_cm_medicao FOREIGN KEY (id_medicao)
        REFERENCES medicao (id_medicao) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE medicao_padrao (
    id_medicao INT UNSIGNED NOT NULL,
    id_padrao INT UNSIGNED NOT NULL,
    lote_utilizacao VARCHAR(30) NOT NULL,
    PRIMARY KEY (id_medicao, id_padrao),
    CONSTRAINT fk_mp_medicao FOREIGN KEY (id_medicao)
        REFERENCES medicao (id_medicao) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_mp_padrao FOREIGN KEY (id_padrao)
        REFERENCES padrao_calibracao (id_padrao) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE historico_evento (
    id_historico INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_certificado INT UNSIGNED NOT NULL,
    id_usuario INT UNSIGNED NOT NULL,
    data_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status_anterior VARCHAR(30) NOT NULL,
    novo_status VARCHAR(30) NOT NULL,
    justificativa_observacao VARCHAR(255) NULL,
    CONSTRAINT fk_he_certificado FOREIGN KEY (id_certificado)
        REFERENCES certificado (id_certificado) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_he_usuario FOREIGN KEY (id_usuario)
        REFERENCES usuario (id_usuario) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE INDEX idx_he_cert_data ON historico_evento(id_certificado, data_hora);

INSERT INTO cliente (id_cliente, razao_social, cnpj, contato, email, telefone, endereco) VALUES
(1, 'Schulz S.A. - Matriz Compressores', '84.693.183/0001-57', 'Carlos Eduardo Silva', 'carlos.silva@schulz.com.br', '(47) 3451-6000', 'Rua Dona Francisca, 6901 - Joinville/SC'),
(2, 'Tupy S.A. Fundicao e Usinagem', '84.683.473/0001-44', 'Roberto Guimaraes', 'roberto.guimaraes@tupy.com.br', '(47) 4009-8111', 'Rua Albano Schmidt, 3400 - Joinville/SC'),
(3, 'WEG Equipamentos Eletricos S.A.', '07.175.725/0001-63', 'Juliana Becker', 'jbecker@weg.net', '(47) 3276-4000', 'Av. Prefeito Waldemar Grubba, 3300 - Jaragua do Sul/SC');

INSERT INTO usuario (id_usuario, nome, email, senha_hash, papel, registro_profissional, ativo) VALUES
(1, 'Gabriel Oliveira Born', 'gabriel.born@schulz.com.br', '$2y$12$setupHashMet01', 'METROLOGISTA', 'TEC-MET-8891/SC', 1),
(2, 'Gustavo Felicio de Lacerda', 'gustavo.lacerda@schulz.com.br', '$2y$12$setupHashMet02', 'METROLOGISTA', 'TEC-MET-8892/SC', 1),
(3, 'Iduilton Junior de Souza Santos', 'iduilton.santos@schulz.com.br', '$2y$12$setupHashMet03', 'METROLOGISTA', 'TEC-MET-8893/SC', 1),
(4, 'Dr. Arnaldo Silveira', 'arnaldo.silveira@schulz.com.br', '$2y$12$setupHashSig01', 'SIGNATARIO', 'CREA-SC-109822-4', 1),
(5, 'Enga. Beatriz Miranda', 'beatriz.miranda@schulz.com.br', '$2y$12$setupHashSig02', 'SIGNATARIO', 'CREA-SC-114509-8', 1);

INSERT INTO instrumento (id_instrumento, tag, descricao, tipo, fabricante, modelo, numero_serie, resolucao_mm, data_calibracao_prevista, id_cliente) VALUES
(1, 'MMC-SCH-001', 'Maquina de Medicao por Coordenadas Tridimensional', 'MMC CNC', 'Zeiss', 'Prismo Ultra 9/12/7', 'ZE-998210-2021', 0.00010, '2026-11-30', 1),
(2, 'MIC-EXT-014', 'Micrometro Externo Digital de Precisao 0-25mm', 'Micrometro', 'Mitutoyo', '293-240-30', 'MT-0091823', 0.00100, '2026-12-01', 1),
(3, 'PAQ-DIG-005', 'Paquimetro Universal Digital 150mm IP67', 'Paquimetro', 'Mitutoyo', '500-752-20', 'MT-882736', 0.01000, '2026-09-30', 2),
(4, 'REL-CMP-003', 'Relogio Comparador Mecanico Milesimal', 'Relogio', 'Mahr', 'Millimess 1003', 'MH-112984', 0.00100, '2026-10-05', 3);

INSERT INTO padrao_calibracao (id_padrao, codigo_identificacao, descricao, certificado_rastreabilidade, validade, incerteza_padrao, orgao_calibrador) VALUES
(1, 'BP-CER-001', 'Jogo de Blocos Padrao Ceramicos Classe 0 (1-100mm)', 'RBC-CERTI-08819/2025', '2027-03-31', 0.00012, 'CERTI / RBC 002'),
(2, 'BP-ACO-002', 'Jogo de Blocos Padrao em Aco Classe K', 'RBC-IPT-10928/2025', '2027-05-15', 0.00008, 'IPT / RBC 001'),
(3, 'ESF-CAL-001', 'Esfera Padrao de Calibracao Tridimensional D=25mm', 'RBC-CERTI-09455/2025', '2027-01-20', 0.00015, 'CERTI / RBC 002');

INSERT INTO certificado (id_certificado, numero, id_instrumento, id_metrologista, id_signatario, data_emissao, data_aprovacao, temperatura_c, umidade_relativa_pct, incerteza_total, resultado, status, observacoes) VALUES
(1, '00417/2026', 1, 1, 4, '2026-09-01', '2026-09-01 14:30:00', 20.10, 52.00, 0.00045, 'APROVADO', 'APROVADO', 'Ensaio volumetrico conforme ISO 10360-2.'),
(2, '00418/2026', 2, 2, 4, '2026-09-02', '2026-09-02 16:15:22', 20.30, 50.50, 0.00120, 'APROVADO', 'APROVADO', 'Afericao dimensional em regime termico controlado.'),
(3, '00425/2026', 3, 3, NULL, '2026-09-12', NULL, 20.40, 53.50, 0.01200, 'APROVADO', 'PENDENTE_APROVACAO', 'Aguardando validacao formal do signatario.'),
(4, '00426/2026', 4, 1, NULL, '2026-09-13', NULL, 20.20, 51.00, 0.00110, 'APROVADO', 'PENDENTE_APROVACAO', 'Ensaio de relogio comparador executado.');

INSERT INTO medicao (id_medicao, ponto_medicao, valor_nominal, valor_medido, erro_encontrado, repetitividade, incerteza) VALUES
(1, 'Bloco Padrao 10.000 mm (Eixo X)', 10.0000, 10.0003, 0.0003, 0.00008, 0.00045),
(2, 'Bloco Padrao 50.000 mm (Eixo Y)', 50.0000, 50.0006, 0.0006, 0.00010, 0.00048),
(3, 'Afericao Paquimetro P1 = 20.000 mm', 20.0000, 20.0100, 0.0100, 0.00200, 0.01200),
(4, 'Curso Relogio Milesimal P1 = 0.500 mm', 0.5000, 0.5008, 0.0008, 0.00015, 0.00110);

INSERT INTO certificado_medicao (id_certificado, id_medicao, ordem_apresentacao) VALUES
(1, 1, 1), (1, 2, 2), (2, 1, 1), (3, 3, 1), (4, 4, 1);

INSERT INTO medicao_padrao (id_medicao, id_padrao, lote_utilizacao) VALUES
(1, 1, 'LOTE-2026-BP01'),
(2, 1, 'LOTE-2026-BP01'),
(3, 2, 'LOTE-2026-BP02'),
(4, 1, 'LOTE-2026-BP01'),
(1, 2, 'LOTE-2026-BP02-CROSS');

INSERT INTO historico_evento (id_historico, id_certificado, id_usuario, data_hora, status_anterior, novo_status, justificativa_observacao) VALUES
(1, 1, 1, '2026-09-01 10:15:00', 'RASCUNHO', 'PENDENTE_APROVACAO', 'Medicoes importadas da MMC finalizadas.'),
(2, 1, 4, '2026-09-01 14:30:00', 'PENDENTE_APROVACAO', 'APROVADO', 'Laudo assinado e liberado.'),
(3, 3, 3, '2026-09-12 14:10:00', 'RASCUNHO', 'PENDENTE_APROVACAO', 'Submetido para aprovacao.'),
(4, 4, 1, '2026-09-13 09:00:00', 'RASCUNHO', 'PENDENTE_APROVACAO', 'Ensaio finalizado.');

SELECT 'cliente' AS tabela, COUNT(*) AS total FROM cliente
UNION ALL SELECT 'usuario', COUNT(*) FROM usuario
UNION ALL SELECT 'instrumento', COUNT(*) FROM instrumento
UNION ALL SELECT 'padrao_calibracao', COUNT(*) FROM padrao_calibracao
UNION ALL SELECT 'certificado', COUNT(*) FROM certificado
UNION ALL SELECT 'medicao', COUNT(*) FROM medicao
UNION ALL SELECT 'certificado_medicao', COUNT(*) FROM certificado_medicao
UNION ALL SELECT 'medicao_padrao', COUNT(*) FROM medicao_padrao
UNION ALL SELECT 'historico_evento', COUNT(*) FROM historico_evento;
