-- MySQL Workbench Forward Engineering

SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

-- -----------------------------------------------------
-- Schema mydb
-- -----------------------------------------------------

-- -----------------------------------------------------
-- Schema mydb
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `BaseDadosGestAI` DEFAULT CHARACTER SET utf8 ;
USE `BaseDadosGestAI` ;

-- -----------------------------------------------------
-- Table `mydb`.`docentes`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `BaseDadosGestAI`.`docentes` (
  `id_docente` INT NOT NULL AUTO_INCREMENT,
  `nome` VARCHAR(100) NULL,
  `tipo_docente` ENUM('carreira', 'contratado') NULL,
  `departamento` ENUM('matemática', 'física', 'gestão') NULL,
  PRIMARY KEY (`id_docente`))
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `mydb`.`templates`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `BaseDadosGestAI`.`templates` (
  `id_template` INT NOT NULL AUTO_INCREMENT,
  `caminho_ficheiro` VARCHAR(225) NULL,
  `tipo_contrato` VARCHAR(50) NULL,
  PRIMARY KEY (`id_template`))
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `mydb`.`carga_horaria`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `BaseDadosGestAI`.`carga_horaria` (
  `id_carga` INT NOT NULL AUTO_INCREMENT,
  `tempo_contratual` DECIMAL(4,1) NULL,
  `tempo_aulas` DECIMAL(4,1) NULL,
  `tempo_apoio` DECIMAL(4,1) NULL,
  `tempo_preparacao` DECIMAL(4,1) NULL,
  `percentagem` DECIMAL(4,1) NULL,
  PRIMARY KEY (`id_carga`))
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `mydb`.`contratos`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `BaseDadosGestAI`.`contratos` (
  `id_contrato` INT NOT NULL AUTO_INCREMENT,
  `data_inicio` DATE NULL,
  `data_fim` DATE NULL,
  `docentes_id_docente` INT NOT NULL,
  `templates_id_template` INT NOT NULL,
  `carga_horaria_id_carga` INT NOT NULL,
  PRIMARY KEY (`id_contrato`),
  INDEX `fk_contratos_docentes_idx` (`docentes_id_docente` ASC) VISIBLE,
  INDEX `fk_contratos_templates1_idx` (`templates_id_template` ASC) VISIBLE,
  INDEX `fk_contratos_carga_horaria1_idx` (`carga_horaria_id_carga` ASC) VISIBLE,
  CONSTRAINT `fk_contratos_docentes`
    FOREIGN KEY (`docentes_id_docente`)
    REFERENCES `mydb`.`docentes` (`id_docente`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_contratos_templates1`
    FOREIGN KEY (`templates_id_template`)
    REFERENCES `mydb`.`templates` (`id_template`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_contratos_carga_horaria1`
    FOREIGN KEY (`carga_horaria_id_carga`)
    REFERENCES `mydb`.`carga_horaria` (`id_carga`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `mydb`.`detalhes_contratados`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `BaseDadosGestAI`.`detalhes_contratados` (
  `iddetalhes_contratados` INT NOT NULL AUTO_INCREMENT,
  `nif` INT NULL,
  `morada` VARCHAR(255) NULL,
  `docentes_id_docente` INT NOT NULL,
  PRIMARY KEY (`iddetalhes_contratados`),
  INDEX `fk_detalhes_contratados_docentes1_idx` (`docentes_id_docente` ASC) VISIBLE,
  CONSTRAINT `fk_detalhes_contratados_docentes1`
    FOREIGN KEY (`docentes_id_docente`)
    REFERENCES `mydb`.`docentes` (`id_docente`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;

-- Criar a tabela 'documentos' que o teu código Python (setup_db.py) está a tentar usar
CREATE TABLE IF NOT EXISTS documentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    caminho VARCHAR(500) NOT NULL,
    categoria VARCHAR(100) NOT NULL,
    data_upload VARCHAR(100) NOT NULL
);

-- Criar a tabela 'rascunhos' (caso já estejas a usar a funcionalidade de guardar contratos a meio)
CREATE TABLE IF NOT EXISTS rascunhos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome_docente VARCHAR(255),
    tipo_contrato VARCHAR(100),
    dados_formulario TEXT NOT NULL,
    data_guardado VARCHAR(100) NOT NULL
);
SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;
