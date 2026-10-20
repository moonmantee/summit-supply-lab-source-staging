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


// Only allow POST requests.
// Typing /order.php directly into the browser is not an order.
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    exit('Method not allowed.');
}


// Read values sent by the order form.
$sku = trim($_POST['sku'] ?? '');

$quantity = filter_input(
    INPUT_POST,
    'quantity',
    FILTER_VALIDATE_INT
);


// Basic input validation.
if ($sku === '') {
    http_response_code(400);
    exit('Invalid product.');
}

if ($quantity === false || $quantity === null || $quantity < 1 || $quantity > 5) {
    http_response_code(400);
    exit('Invalid quantity.');
}


try {

    // Connect to MariaDB on sql01.
    $pdo = new PDO(
        "mysql:host={$config['host']};dbname={$config['database']};charset=utf8mb4",
        $config['username'],
        $config['password'],
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC
        ]
    );


    /*
     * Look up the product.
     *
     * The ? is a placeholder. We supply the actual SKU separately.
     * This is called a prepared statement.
     */
    $stmt = $pdo->prepare(
        "SELECT id, sku, name, description, price, stock
         FROM products
         WHERE sku = ?"
    );

    $stmt->execute([$sku]);

    $product = $stmt->fetch();


    if (!$product) {
        http_response_code(404);
        exit('Product not found.');
    }


    if ((int)$product['stock'] < 1) {
        http_response_code(409);
        exit('This item is currently out of stock.');
    }


    /*
     * Generate a unique identifier for this particular order.
     *
     * Example:
     *
     * WEB-20260912-204522-3A91BF
     */
    $orderToken =
        'WEB-' .
        date('Ymd-His') .
        '-' .
        strtoupper(bin2hex(random_bytes(3)));


    // Store the order in MariaDB.
    $stmt = $pdo->prepare(
        "INSERT INTO orders
            (order_token, product_id, quantity, status)
         VALUES
            (?, ?, ?, 'submitted')"
    );

    $stmt->execute([
        $orderToken,
        $product['id'],
        $quantity
    ]);


    // MariaDB generated this automatically because id uses AUTO_INCREMENT.
    $orderId = $pdo->lastInsertId();


    // Calculate a display total.
    $total = (float)$product['price'] * $quantity;


} catch (PDOException $e) {

    // Put the real error in Apache's server log, not on the public page.
    error_log('Summit order database error: ' . $e->getMessage());

    http_response_code(503);
    exit('Order service temporarily unavailable.');
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

<title>Order Submitted | Summit Supply</title>

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
    max-width:700px;
    margin:80px auto;
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

.product {
    background:var(--sky);
    border-radius:8px;
    padding:22px;
    margin:24px 0;
}

.product h2 {
    margin:0 0 8px;
    font-size:22px;
}

.row {
    display:flex;
    justify-content:space-between;
    gap:20px;
    padding:6px 0;
}

.label {
    color:var(--muted);
}

.token {
    font-family:monospace;
    word-break:break-all;
}

.button {
    display:inline-block;
    margin-top:20px;
    padding:12px 22px;
    background:var(--ink);
    color:white;
    text-decoration:none;
    border-radius:4px;
    font-weight:bold;
}

.notice {
    margin-top:24px;
    color:var(--muted);
    font-size:13px;
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
    Order submitted.
</h1>

<p>
    Your practice order was successfully stored in the
    Summit Supply ordering system.
</p>

<div class="product">

<h2>
    <?= e($product['name']) ?>
</h2>

<div class="row">
    <span class="label">SKU</span>
    <span><?= e($product['sku']) ?></span>
</div>

<div class="row">
    <span class="label">Quantity</span>
    <span><?= (int)$quantity ?></span>
</div>

<div class="row">
    <span class="label">Unit price</span>
    <span>
        $<?= number_format((float)$product['price'], 2) ?>
    </span>
</div>

<div class="row">
    <span class="label">Total</span>
    <strong>
        $<?= number_format($total, 2) ?>
    </strong>
</div>

<div class="row">
    <span class="label">Order ID</span>
    <span><?= e($orderId) ?></span>
</div>

<div class="row">
    <span class="label">Order token</span>
    <span class="token">
        <?= e($orderToken) ?>
    </span>
</div>

</div>

<a
    class="button"
    href="/order-history.php?token=<?= urlencode($orderToken) ?>"
>
    View this order
</a>

<a
    class="button"
    href="/"
>
    Return to catalog
</a>

<p class="notice">
    Practice storefront. No payment was collected.
</p>

</div>

</div>

</body>
</html>
