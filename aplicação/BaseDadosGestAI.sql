-- MySQL dump 10.13  Distrib 8.0.46, for Win64 (x86_64)
--
-- Host: localhost    Database: basedadosgestai
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `areas_estudo`
--

DROP TABLE IF EXISTS `areas_estudo`;
CREATE TABLE `areas_estudo` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4;

LOCK TABLES `areas_estudo` WRITE;
/*!40000 ALTER TABLE `areas_estudo` DISABLE KEYS */;
INSERT INTO `areas_estudo` VALUES (1,'Informática'),(2,'Design'),(3,'Gestão');
/*!40000 ALTER TABLE `areas_estudo` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `carga_horaria`
--

DROP TABLE IF EXISTS `carga_horaria`;
CREATE TABLE `carga_horaria` (
  `id_carga` int NOT NULL AUTO_INCREMENT,
  `tempo_contratual` decimal(4,1) DEFAULT NULL,
  `tempo_aulas` decimal(4,1) DEFAULT NULL,
  `tempo_apoio` decimal(4,1) DEFAULT NULL,
  `tempo_preparacao` decimal(4,1) DEFAULT NULL,
  `percentagem` decimal(4,1) DEFAULT NULL,
  PRIMARY KEY (`id_carga`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4;

LOCK TABLES `carga_horaria` WRITE;
/*!40000 ALTER TABLE `carga_horaria` DISABLE KEYS */;
INSERT INTO `carga_horaria` VALUES
  (1,5.5,2.0,1.0,2.5,16.7),
  (2,7.0,2.5,1.5,3.0,20.8),
  (3,8.5,3.0,2.0,3.5,25.0),
  (4,10.0,3.5,2.0,4.5,29.2),
  (5,11.5,4.0,3.0,4.5,33.3),
  (6,13.0,4.5,3.0,5.5,37.5),
  (7,14.5,5.0,3.0,6.5,41.7),
  (8,16.0,5.5,4.0,6.5,45.8),
  (9,17.5,6.0,4.0,7.5,50.0),
  (10,18.5,6.5,4.0,8.0,54.2),
  (11,20.0,7.0,4.0,9.0,58.3),
  (12,20.5,8.0,4.0,8.5,59.5),
  (13,26.0,9.0,6.0,11.0,75.0),
  (14,29.0,10.0,7.0,12.0,83.3),
  (15,32.0,11.0,8.0,13.0,91.7),
  (16,35.0,12.0,9.0,14.0,100.0);
/*!40000 ALTER TABLE `carga_horaria` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `templates`
-- (criada antes de contratos por causa da FK)
--

DROP TABLE IF EXISTS `templates`;
CREATE TABLE `templates` (
  `id_template` int NOT NULL AUTO_INCREMENT,
  `caminho_ficheiro` varchar(225) DEFAULT NULL,
  `tipo_contrato` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id_template`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4;

LOCK TABLES `templates` WRITE;
/*!40000 ALTER TABLE `templates` DISABLE KEYS */;
INSERT INTO `templates` VALUES
  (1,'Modelos Contratuais/tempo integral anual','Tempo Integral'),
  (2,'Modelos Contratuais/tempo parcial semestral','Tempo Parcial'),
  (3,'Modelos Contratuais/tempo parcial edital','Tempo Parcial Edital'),
  (4,'Modelos Contratuais/Modelos Gerados','Modelos Gerados'),
  (5,'Modelos Contratuais/Em_Processamento','Em Processamento');
/*!40000 ALTER TABLE `templates` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `contratos`
-- Alterações:
--   - Removida data_renovacao (substituída por data_inicio e data_fim)
--   - Adicionadas data_inicio e data_fim (NOT NULL)
--   - FK de templates corrigida: era mydb.templates, agora é templates (mesma BD)
--

DROP TABLE IF EXISTS `contratos`;
CREATE TABLE `contratos` (
  `id_contrato` int NOT NULL AUTO_INCREMENT,
  `numero_renovacao` int DEFAULT 1,
  `contrato_original_id` int DEFAULT NULL,
  `data_inicio` date NOT NULL,
  `data_fim` date NOT NULL,
  `templates_id_template` int NOT NULL,
  `carga_horaria_id_carga` int NOT NULL,
  PRIMARY KEY (`id_contrato`),
  KEY `fk_contratos_templates1_idx` (`templates_id_template`),
  KEY `fk_contratos_carga_horaria1_idx` (`carga_horaria_id_carga`),
  KEY `fk_contratos_original_idx` (`contrato_original_id`),
  CONSTRAINT `fk_contratos_carga_horaria1` FOREIGN KEY (`carga_horaria_id_carga`) REFERENCES `carga_horaria` (`id_carga`),
  CONSTRAINT `fk_contratos_templates1` FOREIGN KEY (`templates_id_template`) REFERENCES `templates` (`id_template`),
  CONSTRAINT `fk_contratos_original` FOREIGN KEY (`contrato_original_id`) REFERENCES `contratos` (`id_contrato`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4;

LOCK TABLES `contratos` WRITE;
/*!40000 ALTER TABLE `contratos` DISABLE KEYS */;
-- (id_contrato, numero_renovacao, contrato_original_id, data_inicio, data_fim, templates_id_template, carga_horaria_id_carga)
INSERT INTO `contratos` VALUES
  (1, 1, NULL, '2025-10-01', '2026-09-30', 1, 16),
  (2, 1, NULL, '2025-10-01', '2026-02-02', 2, 11),
  (3, 1, NULL, '2025-10-01', '2026-02-02', 3, 11);
/*!40000 ALTER TABLE `contratos` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `docentes`
-- Alterações:
--   - Adicionada FK id_contrato -> contratos.id_contrato
--

DROP TABLE IF EXISTS `docentes`;
CREATE TABLE `docentes` (
  `id_docente` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) DEFAULT NULL,
  `tipo_docente` enum('carreira','contratado') DEFAULT NULL,
  `departamento` enum('matemática','física','gestão') DEFAULT NULL,
  `id_contrato` int DEFAULT NULL,
  PRIMARY KEY (`id_docente`),
  KEY `fk_docentes_contratos_idx` (`id_contrato`),
  CONSTRAINT `fk_docentes_contratos` FOREIGN KEY (`id_contrato`) REFERENCES `contratos` (`id_contrato`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4;



--
-- Table structure for table `detalhes_contratados`
-- Alterações:
--   - FK corrigida: era mydb.docentes, agora é docentes (mesma BD)
--

DROP TABLE IF EXISTS `detalhes_contratados`;
CREATE TABLE `detalhes_contratados` (
  `iddetalhes_contratados` int NOT NULL AUTO_INCREMENT,
  `nif` int DEFAULT NULL,
  `morada` varchar(255) DEFAULT NULL,
  `docentes_id_docente` int NOT NULL,
  PRIMARY KEY (`iddetalhes_contratados`),
  KEY `fk_detalhes_contratados_docentes1_idx` (`docentes_id_docente`),
  CONSTRAINT `fk_detalhes_contratados_docentes1` FOREIGN KEY (`docentes_id_docente`) REFERENCES `docentes` (`id_docente`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4;

LOCK TABLES `detalhes_contratados` WRITE;
/*!40000 ALTER TABLE `detalhes_contratados` DISABLE KEYS */;
INSERT INTO `detalhes_contratados` VALUES
  (1,123456789,'Av. Ceuta',1),
  (2,321654987,'Rua da Covilhã',2),
  (3,159478236,'Rua da Seara',3),
  (4,236478159,'Rua do Caminho da Ponte',4);
/*!40000 ALTER TABLE `detalhes_contratados` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cursos`
--

DROP TABLE IF EXISTS `cursos`;
CREATE TABLE `cursos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4;

LOCK TABLES `cursos` WRITE;
/*!40000 ALTER TABLE `cursos` DISABLE KEYS */;
INSERT INTO `cursos` VALUES
  (1,'Licenciatura em Engenharia Informática'),
  (2,'Mestrado em Gestão'),
  (3,'Licenciatura em Engenharia Informática');
/*!40000 ALTER TABLE `cursos` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `ucs`
--

DROP TABLE IF EXISTS `ucs`;
CREATE TABLE `ucs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4;

LOCK TABLES `ucs` WRITE;
/*!40000 ALTER TABLE `ucs` DISABLE KEYS */;
INSERT INTO `ucs` VALUES
  (1,'Programação Web'),
  (2,'Bases de Dados'),
  (3,'Matemática Discreta');
/*!40000 ALTER TABLE `ucs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `documentos`
-- Nota: data_upload alterada para DATETIME para suportar o formato ISO completo dos dados existentes
--

DROP TABLE IF EXISTS `documentos`;
CREATE TABLE `documentos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome` varchar(255) NOT NULL,
  `caminho` varchar(500) NOT NULL,
  `categoria` varchar(100) NOT NULL,
  `data_upload` datetime NOT NULL,
  `contrato_id` int DEFAULT NULL,
  `versao_contrato` int DEFAULT 1,
  PRIMARY KEY (`id`),
  KEY `fk_documentos_contrato_idx` (`contrato_id`),
  CONSTRAINT `fk_documentos_contrato` FOREIGN KEY (`contrato_id`) REFERENCES `contratos` (`id_contrato`)
) ENGINE=InnoDB AUTO_INCREMENT=44 DEFAULT CHARSET=utf8mb4;

LOCK TABLES `documentos` WRITE;
/*!40000 ALTER TABLE `documentos` DISABLE KEYS */;
INSERT INTO `documentos` VALUES
  (1,'0599305998.pdf','pdfs_teste/0599305998.pdf','pdf_llm','2026-05-06 12:11:06',NULL,1),
  (2,'2305823059.pdf','pdfs_teste/2305823059.pdf','pdf_llm','2026-05-06 12:11:06',NULL,1),
  (3,'Alteração ao Regulamento de Contratação de Pessoal.pdf','pdfs_teste/Alteração ao Regulamento de Contratação de Pessoal.pdf','pdf_llm','2026-05-06 12:11:06',NULL,1),
  (4,'Lista verificação renovação prof adjunto TI.DOCX','pdfs_teste/Lista verificação renovação prof adjunto TI.DOCX','pdf_llm','2026-05-06 12:11:06',NULL,1),
  (5,'Lista verificação_Alteração do contrato.docx','pdfs_teste/Lista verificação_Alteração do contrato.docx','pdf_llm','2026-05-06 12:11:06',NULL,1),
  (6,'Lista verificação_Assistente convidado_TP.docx','pdfs_teste/Lista verificação_Assistente convidado_TP.docx','pdf_llm','2026-05-06 12:11:06',NULL,1),
  (7,'Lista verificação_Prof adjunto_TI.docx','pdfs_teste/Lista verificação_Prof adjunto_TI.docx','pdf_llm','2026-05-06 12:11:06',NULL,1),
  (8,'Lista verificação_Prof adjunto_TP.docx','pdfs_teste/Lista verificação_Prof adjunto_TP.docx','pdf_llm','2026-05-06 12:11:06',NULL,1),
  (27,'1. Necessidade da área.docx','Modelos Contratuais/tempo integral anual/1. Necessidade da área.docx','tempo integral anual','2026-05-06 12:11:06',NULL,1),
  (28,'2. Proposta de contratação final.docx','Modelos Contratuais/tempo integral anual/2. Proposta de contratação final.docx','tempo integral anual','2026-05-06 12:11:06',NULL,1),
  (29,'3.  Relatório_Juri.docx','Modelos Contratuais/tempo integral anual/3.  Relatório_Juri.docx','tempo integral anual','2026-05-06 12:11:06',NULL,1),
  (30,'Ficha de serviço atribuido.docx','Modelos Contratuais/tempo integral anual/Ficha de serviço atribuido.docx','tempo integral anual','2026-05-06 12:11:06',NULL,1),
  (31,'1. Necessidade da área_TP.docx','Modelos Contratuais/tempo parcial semestral/1. Necessidade da área_TP.docx','tempo parcial semestral','2026-05-06 12:11:06',NULL,1),
  (32,'2 .Necessidade de contratação_ Juri.docx','Modelos Contratuais/tempo parcial semestral/2 .Necessidade de contratação_ Juri.docx','tempo parcial semestral','2026-05-06 12:11:06',NULL,1),
  (33,'3.  Proposta do Juri.docx','Modelos Contratuais/tempo parcial semestral/3.  Proposta do Juri.docx','tempo parcial semestral','2026-05-06 12:11:06',NULL,1),
  (34,'4. DISPENSA DE CONSTIT DE BOLSA RECRUTA.docx','Modelos Contratuais/tempo parcial semestral/4. DISPENSA DE CONSTIT DE BOLSA RECRUTA.docx','tempo parcial semestral','2026-05-06 12:11:06',NULL,1),
  (35,'5. Proposta de contratação final.docx','Modelos Contratuais/tempo parcial semestral/5. Proposta de contratação final.docx','tempo parcial semestral','2026-05-06 12:11:06',NULL,1),
  (36,'Ficha de serviço atribuido.docx','Modelos Contratuais/tempo parcial semestral/Ficha de serviço atribuido.docx','tempo parcial semestral','2026-05-06 12:11:06',NULL,1),
  (37,'1. Necessidade da área_TP.docx','Modelos Contratuais/tempo parcial edital/1. Necessidade da área_TP.docx','tempo parcial edital','2026-05-06 13:14:13',NULL,1),
  (38,'2 .Necessidade de contratação_Juri.docx','Modelos Contratuais/tempo parcial edital/2 .Necessidade de contratação_Juri.docx','tempo parcial edital','2026-05-06 13:14:13',NULL,1),
  (39,'3. E_EDITAL_tempo-parcial_25_26_Informatica.pdf','Modelos Contratuais/tempo parcial edital/3. E_EDITAL_tempo-parcial_25_26_Informatica.pdf','tempo parcial edital','2026-05-06 13:14:13',NULL,1),
  (40,'3b. E Critérios de seleção_edital_diccf_25_26_Informatica.docx','Modelos Contratuais/tempo parcial edital/3b. E Critérios de seleção_edital_diccf_25_26_Informatica.docx','tempo parcial edital','2026-05-06 13:14:13',NULL,1),
  (41,'4 Ata de Seleção_25set 2024_Informática.docx','Modelos Contratuais/tempo parcial edital/4 Ata de Seleção_25set 2024_Informática.docx','tempo parcial edital','2026-05-06 13:14:13',NULL,1),
  (42,'5. Proposta de contratação final.docx','Modelos Contratuais/tempo parcial edital/5. Proposta de contratação final.docx','tempo parcial edital','2026-05-06 13:14:13',NULL,1),
  (43,'Ficha de serviço atribuido.docx','Modelos Contratuais/tempo parcial edital/Ficha de serviço atribuido.docx','tempo parcial edital','2026-05-06 13:14:13',NULL,1);
/*!40000 ALTER TABLE `documentos` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `rascunhos`
--

DROP TABLE IF EXISTS `rascunhos`;
CREATE TABLE `rascunhos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nome_docente` varchar(255) DEFAULT NULL,
  `tipo_contrato` varchar(100) DEFAULT NULL,
  `dados_formulario` text NOT NULL,
  `data_guardado` datetime NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4;



/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;
/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed