<?php
include "db.php";

$usuario = $_POST['usuario'];
$senha = md5($_POST['senha']);

$sql = "SELECT * FROM admin WHERE usuario='$usuario' AND senha='$senha'";
$result = pg_query($conn, $sql);

if (pg_num_rows($result) > 0) {
    header("Location: ../admin/dashboard.php");
} else {
    echo "Login inválido";
}
?>