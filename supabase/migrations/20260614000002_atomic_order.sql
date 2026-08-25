-- ============================================================
-- ALYASMEEN AuntOps — Atomic Order Creation Logic
-- ============================================================

-- Atomic Order Creation Function
-- This function ensures that an order and its line items are created in a single transaction.
-- It also records the event in the audit log.
CREATE OR REPLACE FUNCTION create_order_atomic(
  p_phone TEXT,
  p_fulfillment TEXT,
  p_address TEXT,
  p_total NUMERIC,
  p_items JSONB -- Array of {product_name, qty, unit_price, line_total}
) RETURNS INT AS $$
DECLARE
  v_order_id INT;
  v_order_name TEXT;
  v_item RECORD;
BEGIN
  -- 1. Insert the main order with a temporary name
  INSERT INTO orders (phone, fulfillment, address, total, status)
  VALUES (p_phone, p_fulfillment, p_address, p_total, 'to_do')
  RETURNING id INTO v_order_id;

  -- 2. Generate and update the order name
  v_order_name := 'ORD-' || LPAD(v_order_id::TEXT, 4, '0');
  UPDATE orders SET order_name = v_order_name WHERE id = v_order_id;

  -- 3. Insert order lines from the JSON array
  FOR v_item IN SELECT * FROM jsonb_array_elements(p_items) LOOP
    INSERT INTO order_lines (order_id, product_name, qty, unit_price, line_total)
    VALUES (
      v_order_id,
      v_item.value->>'product_name',
      (v_item.value->>'qty')::INT,
      (v_item.value->>'unit_price')::NUMERIC,
      (v_item.value->>'line_total')::NUMERIC
    );
  END LOOP;

  -- 4. Record in audit log
  INSERT INTO audit_logs (actor, action, details)
  VALUES (p_phone, 'order_created', jsonb_build_object('order_id', v_order_id, 'order_name', v_order_name, 'total', p_total));

  RETURN v_order_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant execution to authenticated users and anon (if bot uses it)
-- Note: In Wave 2 Task 2 we will refine these roles.
GRANT EXECUTE ON FUNCTION create_order_atomic TO anon, authenticated, service_role;
