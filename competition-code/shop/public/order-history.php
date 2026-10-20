<?php

$config = require '/etc/summit-shop/database.php';

function e($value): string
{
    return htmlspecialchars(
        (string)$value,
        ENT_QUOTES | ENT_SUBSTITUTE,
        'UTF-8'
    );
}

$order = null;
$error = null;

$token = trim($_GET['token'] ?? '');

if ($token !== '') {

    try {

        $pdo = new PDO(
            "mysql:host={$config['host']};dbname={$config['database']};charset=utf8mb4",
            $config['username'],
            $config['password'],
            [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC
            ]
        );

        $stmt = $pdo->prepare(
            "SELECT
                orders.id AS order_id,
                orders.order_token,
                orders.quantity,
                orders.status,
                orders.created_at,
                products.sku,
                products.name,
                products.price
             FROM orders
             JOIN products
                ON orders.product_id = products.id
             WHERE orders.order_token = ?"
        );

        $stmt->execute([$token]);

        $order = $stmt->fetch();

        if (!$order) {
            $error = 'No order was found with that token.';
        }

    } catch (PDOException $e) {

        error_log(
            'Summit order lookup database error: ' .
            $e->getMessage()
        );

        http_response_code(503);

        $error = 'Order lookup is temporarily unavailable.';
    }
}

?>
<!doctype html>
<html lang="en">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<title>Order Lookup | Summit Supply</title>

<style>

:root {
    --ink:#123d46;
    --blue:#216277;
    --sky:#d9edf2;
    --paper:#f7faf9;
    --yellow:#efbf47;
    --muted:#496770;
}

* {
    box-sizing:border-box;
}

body {
    margin:0;
    background:var(--paper);
    color:var(--ink);
    font-family:Arial,Helvetica,sans-serif;
}

.wrap {
    max-width:720px;
    margin:70px auto;
    padding:0 24px;
}

.card {
    background:white;
    border:1px solid #d7e2e4;
    border-radius:8px;
    padding:36px;
}

.eyebrow {
    color:var(--blue);
    font-size:12px;
    font-weight:bold;
    letter-spacing:.16em;
    text-transform:uppercase;
}

h1 {
    font-family:Georgia,serif;
    font-weight:normal;
    font-size:42px;
    margin:12px 0 24px;
}

form {
    margin:28px 0;
}

label {
    display:block;
    font-weight:bold;
    margin-bottom:8px;
}

input[type="text"] {
    width:100%;
    padding:12px;
    border:1px solid #b9cdd1;
    border-radius:4px;
    font:inherit;
}

button {
    margin-top:12px;
    padding:12px 20px;
    border:0;
    border-radius:4px;
    background:var(--ink);
    color:white;
    font:inherit;
    font-weight:bold;
    cursor:pointer;
}

button:hover {
    background:var(--blue);
}

.result {
    background:var(--sky);
    border-radius:8px;
    padding:22px;
    margin-top:28px;
}

.row {
    display:flex;
    justify-content:space-between;
    gap:20px;
    padding:7px 0;
    border-bottom:1px solid rgba(18,61,70,.12);
}

.row:last-child {
    border-bottom:0;
}

.label {
    color:var(--muted);
}

.token {
    font-family:monospace;
    word-break:break-all;
}

.error {
    margin-top:24px;
    padding:14px;
    border:1px solid #cda3a3;
    border-radius:4px;
}

.button {
    display:inline-block;
    margin-top:24px;
    padding:12px 20px;
    border-radius:4px;
    background:var(--ink);
    color:white;
    text-decoration:none;
    font-weight:bold;
}

</style>

</head>

<body>

<div class="wrap">

<div class="card">

<div class="eyebrow">
    Summit Supply
</div>

<h1>
    Order lookup
</h1>

<p>
    Enter the order token from your test-order confirmation.
</p>

<form method="get" action="/order-history.php">

<label for="token">
    Order token
</label>

<input
    type="text"
    id="token"
    name="token"
    value="<?= e($token) ?>"
    placeholder="WEB-20260912-204522-3A91BF"
    required
>

<button type="submit">
    Find Order
</button>

</form>


<?php if ($error): ?>

<div class="error">
    <?= e($error) ?>
</div>

<?php endif; ?>


<?php if ($order): ?>

<div class="result">

<div class="row">
    <span class="label">Order ID</span>
    <span><?= (int)$order['order_id'] ?></span>
</div>

<div class="row">
    <span class="label">Order token</span>
    <span class="token">
        <?= e($order['order_token']) ?>
    </span>
</div>

<div class="row">
    <span class="label">Product</span>
    <span><?= e($order['name']) ?></span>
</div>

<div class="row">
    <span class="label">SKU</span>
    <span><?= e($order['sku']) ?></span>
</div>

<div class="row">
    <span class="label">Quantity</span>
    <span><?= (int)$order['quantity'] ?></span>
</div>

<div class="row">
    <span class="label">Unit price</span>
    <span>
        $<?= number_format((float)$order['price'], 2) ?>
    </span>
</div>

<div class="row">
    <span class="label">Status</span>
    <span><?= e($order['status']) ?></span>
</div>

<div class="row">
    <span class="label">Created</span>
    <span><?= e($order['created_at']) ?></span>
</div>

</div>

<?php endif; ?>


<a class="button" href="/">
    Return to catalog
</a>

</div>

</div>

</body>
</html>
