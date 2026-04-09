<?php
include "../backend/db.php";
$result = pg_query($conn, "SELECT * FROM contatos ORDER BY data_envio DESC");
?>

<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Painel Admin</title>
<link rel="style.css" href="style.css">
</head>
<body>

<div class="pagina">
<h2>Mensagens Recebidas</h2>

<table borde ="1" width="100%" cellpadding="10">
<tr>
<th>Nome</th>
<th>Email</th>
<th>Mensagem</th>
<th>Data</th>
</tr>

<?php while($row = pg_fetch_assoc($result)) { ?>
<tr>
<td><?= $row['nome'] ?></td>
<td><?= $row['email'] ?></td>
<td><?= $row['mensagem'] ?></td>
<td><?= $row['data_envio'] ?></td>
</tr>
<?php } ?>

</table>
</div>

</body>
</html>