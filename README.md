# AeroCargo — Customer Portal + Backend API

## Start in VS Code (Windows)
1. Extract this ZIP. Open the **aerocargo_app** folder in VS Code.
2. Select **Terminal → New Terminal**.
3. Check Python: `python --version`. Python 3.9 or newer is required.
4. Start the app:
   ```sh
   python server.py
   ```
   If Windows recognizes `py` instead of `python`, use `py server.py`.
5. Open **http://127.0.0.1:8000** in your browser.
6. Sign in with any valid email and nonempty password (demo login).

No Node.js, npm, pip installs or additional packages are required. This backend uses Python's standard library. If Python is missing, install it from https://www.python.org/downloads/ and enable the installer option to add Python to PATH, then restart VS Code.

Keep the terminal running. Press Ctrl+C to stop. Do not open index.html directly or use Live Server. The Python server serves both the frontend and API. If port 8000 is busy, run `python server.py --port 8001`, open http://127.0.0.1:8001 and change Postman's baseUrl accordingly.

## Test in Postman
Use Postman desktop, or Postman web with its Desktop Agent, to reach localhost.
1. Start the server with `python server.py`.
2. In Postman select **Import → Files** and select `AeroCargo.postman_collection.json`.
3. Open **AeroCargo API Practice**. `baseUrl` is already set to `http://127.0.0.1:8000`.
4. Run requests in numbered order, or use Collection Runner.
5. **03 Create shipment** automatically saves the returned ID to the collection variable `shipmentId`.
6. Check each request's response and test results. Negative cases are expected to return 422 or 404; those are passing tests.

For your first manual request, send **GET http://127.0.0.1:8000/api/health**. Expect HTTP 200 and `{"status":"ok","demo":true}`.

For manual creation, send **POST http://127.0.0.1:8000/api/shipments**, choose **Body → raw → JSON**, and paste `shipment-example.json`. Expect 201. Use the returned `id` in the retrieve, update and quotes URLs.

## API endpoints
| Method | Path | Result |
|---|---|---|
| GET | /api/health | Backend health |
| POST | /api/shipments/import | Parse `{ "text": "..." }` into partial shipment fields |
| POST | /api/shipments | Validate and save a shipment (201) |
| GET | /api/shipments | List stored shipments |
| GET | /api/shipments/{id} | Retrieve one shipment |
| PUT | /api/shipments/{id} | Replace editable details; send the full shipment body |
| GET | /api/shipments/{id}/quotes | Two sample quotations in USD |

JSON bodies require `Content-Type: application/json`. Errors follow `{"error":{"message":"...","details":[]}}`. Validation errors have field-level details. Statuses: 400 malformed JSON; 403 disallowed origin; 404 not found; 405 unsupported method; 413 body over 64 KB; 415 wrong content type; 422 invalid input; 500 server/storage error.

## API documentation
Open **http://127.0.0.1:8000/docs** for Swagger UI and its Try it out controls. Swagger's display assets require internet access; the app and API do not. You can also import the bundled `openapi.json` into Postman if Swagger cannot load.

## Portal workflow
- Shipment Importer starts empty. Paste `import-example.txt` into it.
- After a short pause the portal calls **POST /api/shipments/import** and fills recognized fields. Check missing details manually.
- Click **Search Rates**, review the information, accept the demo terms and click **Submit Request**.
- Submission calls **POST /api/shipments**, then fetches **GET /api/shipments/{id}/quotes**. The displayed request number is the backend shipment UUID.
- Quote figures returned by the server are used by the portal.
- The existing Book Quote, booking history and metrics screens remain browser-local simulations. They do not call airline APIs or create real bookings. Retrieve all saved API shipments through GET /api/shipments.

## Import and calculation rules
The importer supports labeled pickup address, origin/destination airport codes, expected drop-off, cargo type, known shipper, commodity, weight mode, units, pieces, dimensions, weight and handling/packing. It is a rule-based parser, not AI. Unsupported text returns no matches; it does not guess missing required details.

- Dimensions: `48 x 40 x 45 in`, or separate Length/Width/Height lines.
- Units: cm/in and kg/lb, alongside values or on a `Units: in / lb` line.
- Dates: importer accepts DD-MM-YYYY or YYYY-MM-DD; saved API shipment uses YYYY-MM-DD. Calendar validity is checked; past dates are permitted for test data.
- Gross mode means total weight **per cargo row**; piece mode means weight **per piece**.
- A single imported gross weight is distributed across pieces when piece mode is explicitly selected.
- Multiple dimension lines produce multiple cargo rows; enter row weights manually.
- Handling / Packing: Yes means stackable; No means non-stackable.
- Origin airport is not inferred from a postal address. Supply `Origin: LAX` in the importer or API payload.
- Totals `gross`, `volume`, and `charge` are in lb; `kg` is chargeable kg. The demo preserves the existing volumetric divisor of 366 cubic inches per lb. Live carriers may use different rules.
- The importer box stays independent of manual field edits. Clearing it does not erase the form.

## Storage and scope
Shipments are saved in `data/shipments.json`, created on the first successful save. They persist after restart. The server uses atomic file replacement and supports one local process. The built-in HTTP server is intended for local practice. This is a small local learning backend, not a production multi-user system. Login is still simulated; no authentication or per-user record isolation is implemented. The server binds to 127.0.0.1. All quotation rates are samples.

## Automated checks
```sh
python -m unittest discover -s tests -v
```
The tests use a temporary data directory and check live HTTP requests: parsing, creation, retrieval, updates, quotations, validation, error codes, private-file protection, and persistence after restart. They do not alter your saved shipments. Browser automation was not executed in the build environment because a browser executable was unavailable.

## Main files
- `server.py`: local HTTP API, validation, calculations and storage.
- `shipment_importer.py`: shipment text parser.
- `api-client.js`: frontend API requests and shipment submission.
- `app.js`, `importer.js`, `index.html`, `style.css`: customer portal and importer UI.
- `openapi.json`, `docs.html`: API specification and Swagger UI.
- `AeroCargo.postman_collection.json`: 12 requests with assertions.
- `shipment-example.json`, `import-example.txt`: ready-to-use test data.
- `tests/test_api.py`: automated Python HTTP integration tests.
