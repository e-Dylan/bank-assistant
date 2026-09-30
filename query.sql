WITH category_totals AS (
    SELECT
        customer_id,
        category,
        SUM(amount) AS total
    FROM transactions
    WHERE status = 'completed'
    GROUP BY customer_id, category
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total DESC
        ) AS rn
    FROM category_totals
)
SELECT
    customer_id,
    category,
    total
FROM ranked
WHERE rn = 1;