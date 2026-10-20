-- Example for a NEW disposable lab. Set a fresh password before use.
-- These are required business privileges, not every deliberately vulnerable starting grant.
CREATE USER 'shop_app'@'10.77.30.10' IDENTIFIED BY 'REPLACE_AT_DEPLOYMENT';
GRANT SELECT, INSERT, UPDATE, DELETE ON summit_shop.* TO 'shop_app'@'10.77.30.10';
