WITH scanned AS (
    SELECT *, row_number() OVER ()::BIGINT AS source_row_number
    FROM read_csv('{{source_path}}', header=true, auto_detect=false,
        columns={
            'order_id':'VARCHAR','member_id':'VARCHAR','product_id':'VARCHAR',
            'channel':'VARCHAR','order_status':'VARCHAR','quantity':'VARCHAR',
            'currency':'VARCHAR','amount':'VARCHAR','coupon_discount':'VARCHAR',
            'order_created_at':'VARCHAR','departure_date':'VARCHAR','updated_at':'VARCHAR'
        }, nullstr='__LION_NULL_SENTINEL__', strict_mode=true)
), hashed AS (
    SELECT *, sha256(to_json(struct_pack(
        order_id:=order_id, member_id:=member_id, product_id:=product_id, channel:=channel,
        order_status:=order_status, quantity:=quantity, currency:=currency, amount:=amount,
        coupon_discount:=coupon_discount, order_created_at:=order_created_at,
        departure_date:=departure_date, updated_at:=updated_at))) AS row_hash
    FROM scanned
)
INSERT INTO raw.order_event
SELECT order_id, member_id, product_id, channel, order_status, quantity, currency, amount,
       coupon_discount, order_created_at, departure_date, updated_at,
       '{{source_file}}', source_row_number, {{batch_order}}, row_hash,
       sha256('{{source_file}}|' || source_row_number::VARCHAR || '|' || row_hash),
       current_timestamp
FROM hashed;
