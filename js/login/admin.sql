CREATE TABLE admin (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(50),
    senha VARCHAR(255)
);

INSERT INTO admin (usuario, senha)
VALUES ('admin', md5('1234'));