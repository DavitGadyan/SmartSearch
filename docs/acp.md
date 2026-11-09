# Agentic Commerce Protocol (ACP)

The store is a merchant that AI agents can buy from. It implements the merchant side of the
[Agentic Checkout Specification](https://github.com/agentic-commerce-protocol/agentic-commerce-protocol) 2025-09-29
(OpenAI and Stripe, Apache 2.0) plus a JSON product feed and a **mock** delegated-payment provider. The storefront
cart and the in-store assistant are clients of the same endpoints, so one checkout implementation serves humans and
agents.

Base URL: `http://localhost:8000/acp`. Code: `backend/app/api/v1/acp.py`, `backend/app/services/acp_service.py`,
tests in `backend/tests/test_acp.py`.

## Headers

| Header | Value |
|---|---|
| `Authorization` | `Bearer <ACP_API_KEY>` (`dev-acp-key` by default) |
| `API-Version` | `2025-09-29` (anything else → 400) |
| `Idempotency-Key` | recommended on create / complete / delegate; same key + same body replays, different body → 409 `idempotency_conflict` |
| `Request-Id` | echoed back |

Errors are the flat spec object: `{"type", "code", "message", "param"}`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/checkout_sessions` | create (201) from `items[{id, quantity}]`, optional `buyer`, `fulfillment_address` |
| `GET` | `/checkout_sessions/{id}` | read |
| `POST` | `/checkout_sessions/{id}` | update `items`, `buyer`, `fulfillment_address`, `fulfillment_option_id` |
| `POST` | `/checkout_sessions/{id}/complete` | pay with `payment_data.token`; returns `status: completed` and `order{id, checkout_session_id, permalink_url}` |
| `POST` | `/checkout_sessions/{id}/cancel` | 405 once completed or canceled |
| `POST` | `/agentic_commerce/delegate_payment` | mock PSP: test cards `4242…` / `5555…` only, returns `vt_…` token bound to an `allowance` |
| `GET` | `/feed.json?offset&limit` | Product Feed (id, title, description, link, image_url, price, currency, availability, brand, category, reviews …) |

Session object: `id, payment_provider, status, currency, line_items[], fulfillment_address, fulfillment_options[],
fulfillment_option_id, totals[], messages[], links[]`. Amounts are integers in cents. Status moves from
`not_ready_for_payment` to `ready_for_payment` once an address and a shipping option are set and no line item has an
error message (unknown or out-of-stock product), then to `completed` or `canceled`.

Store rules (demo values): flat 8% tax; standard shipping $9.99, free from $75; express $19.99.

## Walkthrough

```sh
H=(-H "Authorization: Bearer dev-acp-key" -H "API-Version: 2025-09-29" -H "Content-Type: application/json")

# 1. create a session for one product, with the shopper's address
curl -s -X POST localhost:8000/acp/checkout_sessions "${H[@]}" -H "Idempotency-Key: demo-1" -d '{
  "items": [{"id": "39786", "quantity": 1}],
  "fulfillment_address": {"name": "Demo Shopper", "line_one": "1 Market Street", "city": "San Francisco",
                          "state": "CA", "country": "US", "postal_code": "94105"}}'
# → status not_ready_for_payment, fulfillment_options [standard, express], totals

# 2. choose shipping → ready_for_payment
curl -s -X POST localhost:8000/acp/checkout_sessions/$SID "${H[@]}" -d '{"fulfillment_option_id": "standard"}'

# 3. obtain a delegated payment token for at most the total (mock PSP)
curl -s -X POST localhost:8000/acp/agentic_commerce/delegate_payment "${H[@]}" -d '{
  "payment_method": {"type": "card", "number": "4242424242424242", "exp_month": "12", "exp_year": "2030", "metadata": {}},
  "allowance": {"reason": "one_time", "max_amount": 21491, "currency": "usd",
                "checkout_session_id": "'$SID'", "merchant_id": "smartsearch-demo", "expires_at": "2027-01-01T00:00:00Z"},
  "metadata": {"source": "my-agent"}}'
# → {"id": "vt_…", "created": …}

# 4. complete → an order in the store (orders, order_items, purchase events with source acp:my-agent)
curl -s -X POST localhost:8000/acp/checkout_sessions/$SID/complete "${H[@]}" -d '{"payment_data": {"token": "'$TOKEN'"}}'
```

The token is checked for currency, expiry, `max_amount ≥ total`, single use and session binding. When
`ACP_WEBHOOK_URL` is set, `order_create` is POSTed with an HMAC-SHA256 `Merchant-Signature`.

## Inside the store

- **Cart page**: checkout = create session → address and shipping → delegated token → complete. The success page
  says "Completed through the Agentic Commerce Protocol".
- **Assistant**: `start_checkout` prices the items (or the browser cart, which the page sends with each message) and
  the agent asks for confirmation; `complete_checkout` runs only after an explicit yes, then the cart is cleared
  and the order id is shown. Purchases carry `source = acp:assistant`.

## What is mocked

No real payment provider is involved. `delegate_payment` accepts two test card numbers, never stores a PAN and keeps
only brand, last four digits and funding type for display. Addresses are not validated. Taxes and shipping are fixed
demo rules.
