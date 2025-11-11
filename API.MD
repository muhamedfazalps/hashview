# Hashview API Documentation

This document provides comprehensive documentation for all API endpoints available in Hashview.

## Table of Contents
- [Authentication](#authentication)
- [Admin Endpoints](#admin-endpoints)
- [Agent Endpoints](#agent-endpoints)
- [Customer Endpoints](#customer-endpoints)
- [Rules Endpoints](#rules-endpoints)
- [Wordlist Endpoints](#wordlist-endpoints)
- [Job Endpoints](#job-endpoints)
- [Task Endpoints](#task-endpoints)
- [Hashfile Endpoints](#hashfile-endpoints)
- [Hash Management Endpoints](#hash-management-endpoints)
- [Search Endpoints](#search-endpoints)
- [Error Reporting Endpoints](#error-reporting-endpoints)

---

## Authentication

All API endpoints require authentication via cookies. There are two types of authentication:

1. **User Authentication**: Uses `uuid` cookie containing the user's API key
2. **Agent Authentication**: Uses `uuid` cookie containing the agent's UUID

Set authentication by including the UUID in the request cookies:
```bash
Cookie: uuid=<your-api-key-or-agent-uuid>
```

---

## Admin Endpoints

### Get Admin Settings

**Endpoint**: `GET /v1/admin/settings`

**Authorization**: User or Agent

**Description**: Retrieves all system settings.

**Response**:
```json
{
  "status": 200,
  "settings": "[{\"id\": 1, \"setting_name\": \"value\", ...}]"
}
```

**Example**:
```bash
curl -X GET http://localhost:5000/v1/admin/settings \
  -b "uuid=your-api-key"
```

---

## Agent Endpoints

### Agent Heartbeat

**Endpoint**: `POST /v1/agents/heartbeat`

**Authorization**: Agent only

**Description**: Agents use this endpoint to register themselves, update their status, and receive task assignments. The server checks agent version compatibility and maximum runtime limits.

**Request Body**:
```json
{
  "agent_status": "Idle|Working",
  "hc_status": "{\"Speed #\": \"12345 H/s\", ...}"
}
```

**Response** (when idle and task available):
```json
{
  "status": 200,
  "type": "message",
  "msg": "START",
  "job_task_id": 123
}
```

**Response** (when working):
```json
{
  "status": 200,
  "type": "message",
  "msg": "OK"
}
```

**Response** (task canceled):
```json
{
  "status": 200,
  "type": "message",
  "msg": "Canceled"
}
```

**Response** (new agent registration):
```json
{
  "status": 200,
  "type": "message",
  "msg": "Go Away"
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/v1/agents/heartbeat \
  -H "Content-Type: application/json" \
  -b "uuid=agent-uuid; agent_version=0.8.0; name=agent-01" \
  -d '{
    "agent_status": "Idle",
    "hc_status": ""
  }'
```

---

## Customer Endpoints

### Get All Customers

**Endpoint**: `GET /v1/customers`

**Authorization**: User or Agent

**Description**: Retrieves a list of all customers.

**Response**:
```json
{
  "status": 200,
  "users": "[{\"id\": 1, \"name\": \"Customer Name\", \"description\": \"...\"}]"
}
```

**Example**:
```bash
curl -X GET http://localhost:5000/v1/customers \
  -b "uuid=your-api-key"
```

### Add Customer

**Endpoint**: `POST /v1/customers/add`

**Authorization**: User only

**Description**: Creates a new customer entry.

**Request Body**:
```json
{
  "name": "Acme Corporation",
  "description": "Client for Q4 2024"
}
```

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "Customer added",
  "customer_id": 5
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/v1/customers/add \
  -H "Content-Type: application/json" \
  -b "uuid=your-api-key" \
  -d '{
    "name": "Acme Corporation",
    "description": "Client for Q4 2024"
  }'
```

---

## Rules Endpoints

### Get All Rules

**Endpoint**: `GET /v1/rules`

**Authorization**: User or Agent

**Description**: Retrieves all hashcat rule files.

**Response**:
```json
{
  "status": 200,
  "rules": "[{\"id\": 1, \"name\": \"best64\", \"path\": \"/path/to/rules\"}]"
}
```

**Example**:
```bash
curl -X GET http://localhost:5000/v1/rules \
  -b "uuid=your-api-key"
```

### Download Rules File

**Endpoint**: `GET /v1/rules/<int:rules_id>`

**Authorization**: User or Agent

**Description**: Downloads a specific rules file (gzip compressed).

**Response**: Binary file (application/octet-stream)

**Example**:
```bash
curl -X GET http://localhost:5000/v1/rules/1 \
  -b "uuid=your-api-key" \
  -o rules.gz
```

---

## Wordlist Endpoints

### Get All Wordlists

**Endpoint**: `GET /v1/wordlists`

**Authorization**: User or Agent

**Description**: Retrieves all available wordlists.

**Response**:
```json
{
  "status": 200,
  "wordlists": "[{\"id\": 1, \"name\": \"rockyou\", \"path\": \"...\", \"size\": 14344391}]"
}
```

**Example**:
```bash
curl -X GET http://localhost:5000/v1/wordlists \
  -b "uuid=your-api-key"
```

### Download Wordlist

**Endpoint**: `GET /v1/wordlists/<int:wordlist_id>`

**Authorization**: User or Agent

**Description**: Downloads a specific wordlist file (gzip compressed).

**Response**: Binary file (application/octet-stream)

**Example**:
```bash
curl -X GET http://localhost:5000/v1/wordlists/1 \
  -b "uuid=your-api-key" \
  -o wordlist.gz
```

### Update Dynamic Wordlist

**Endpoint**: `GET /v1/updateWordlist/<int:wordlist_id>`

**Authorization**: User or Agent

**Description**: Triggers an update for a dynamic wordlist (refreshes content from cracked hashes).

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "OK"
}
```

**Example**:
```bash
curl -X GET http://localhost:5000/v1/updateWordlist/3 \
  -b "uuid=your-api-key"
```

### Add Wordlist

**Endpoint**: `POST /v1/wordlists/add/<wordlist_name>`

**Authorization**: User or Agent

**Description**: Creates a new wordlist by uploading plain text content.

**Request Body**: Raw plain text (one word per line)

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "Wordlist added",
  "wordlist_id": 10
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/v1/wordlists/add/custom_wordlist \
  -H "Content-Type: text/plain" \
  -b "uuid=your-api-key" \
  --data-binary @wordlist.txt
```

---

## Job Endpoints

### Get Job Details

**Endpoint**: `GET /v1/jobs/<int:job_id>`

**Authorization**: User or Agent

**Description**: Retrieves details about a specific job.

**Response**:
```json
{
  "status": 200,
  "job": "{\"id\": 1, \"name\": \"Job Name\", \"status\": \"Queued\", \"hashfile_id\": 5}"
}
```

**Example**:
```bash
curl -X GET http://localhost:5000/v1/jobs/1 \
  -b "uuid=your-api-key"
```

### Add Job

**Endpoint**: `POST /v1/jobs/add`

**Authorization**: User only

**Description**: Creates a new cracking job. The system automatically assigns the top 10 most effective tasks based on historical data for the hash type.

**Request Body**:
```json
{
  "name": "Q4 Password Audit",
  "hashfile_id": 5,
  "customer_id": 3,
  "limit_recovered": false,
  "notify_email": true,
  "notify_pushover": false
}
```

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "Job added",
  "job_id": 42
}
```

**Error Response** (insufficient training data):
```json
{
  "status": 500,
  "type": "Error",
  "msg": "Not enough data to determine effective tasks for this hash type. Please add more cracked hashes of this type before creating a job."
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/v1/jobs/add \
  -H "Content-Type: application/json" \
  -b "uuid=your-api-key" \
  -d '{
    "name": "Q4 Password Audit",
    "hashfile_id": 5,
    "customer_id": 3,
    "limit_recovered": true,
    "notify_email": true,
    "notify_pushover": false
  }'
```

### Start Job

**Endpoint**: `POST /v1/jobs/start/<int:job_id>`

**Authorization**: User only

**Description**: Starts a job by queuing all its tasks. Only job owners or admins can start jobs.

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "Job started",
  "job_id": 42
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/v1/jobs/start/42 \
  -b "uuid=your-api-key"
```

---

## Task Endpoints

### Get Task Details

**Endpoint**: `GET /v1/tasks/<int:task_id>`

**Authorization**: User or Agent

**Description**: Retrieves details about a specific task configuration.

**Response**:
```json
{
  "status": 200,
  "task": "{\"id\": 1, \"name\": \"Task Name\", \"wl_id\": 1, \"rule_id\": 2}"
}
```

**Example**:
```bash
curl -X GET http://localhost:5000/v1/tasks/1 \
  -b "uuid=your-api-key"
```

### Get Job Task Assignment

**Endpoint**: `GET /v1/jobTasks/<int:job_task_id>`

**Authorization**: User or Agent

**Description**: Retrieves details about a specific job task assignment (used by agents).

**Response**:
```json
{
  "status": 200,
  "job_task": "{\"id\": 123, \"job_id\": 42, \"task_id\": 1, \"status\": \"Running\"}"
}
```

**Example**:
```bash
curl -X GET http://localhost:5000/v1/jobTasks/123 \
  -b "uuid=agent-uuid"
```

### Update Job Task Status

**Endpoint**: `POST /v1/jobtask/status`

**Authorization**: Agent only

**Description**: Updates the status of a job task (used by agents to report progress).

**Request Body**:
```json
{
  "job_task_id": 123,
  "task_status": "Completed"
}
```

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "OK"
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/v1/jobtask/status \
  -H "Content-Type: application/json" \
  -b "uuid=agent-uuid" \
  -d '{
    "job_task_id": 123,
    "task_status": "Completed"
  }'
```

---

## Hashfile Endpoints

### Upload Hashfile

**Endpoint**: `POST /v1/hashfiles/upload/<int:customer_id>/<int:file_format>/<int:hash_type>/<hashfile_name>`

**Authorization**: User only

**Description**: Uploads a hashfile for cracking. The system validates the format and automatically detects "insta-cracked" hashes (already in database).

**URL Parameters**:
- `customer_id`: Customer ID
- `file_format`:
  - `0` = pwdump
  - `1` = NetNTLM
  - `2` = kerberos
  - `3` = shadow
  - `4` = user:hash
  - `5` = hash_only
- `hash_type`: Hashcat hash type (e.g., 1000 for NTLM)
- `hashfile_name`: Display name for the hashfile

**Request Body**: Raw plain text (hashfile content)

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "Hashfile added",
  "hashfile_id": 15,
  "hash_count": 1250,
  "instacracked": 342
}
```

**Example**:
```bash
curl -X POST "http://localhost:5000/v1/hashfiles/upload/3/0/1000/DomainHashes" \
  -H "Content-Type: text/plain" \
  -b "uuid=your-api-key" \
  --data-binary @hashes.txt
```

### Download Hashfile

**Endpoint**: `GET /v1/hashfiles/<int:hashfile_id>`

**Authorization**: User or Agent

**Description**: Generates and downloads a hashfile containing only uncracked hashes (used by agents for cracking).

**Response**: Plain text file containing uncracked hashes

**Example**:
```bash
curl -X GET http://localhost:5000/v1/hashfiles/15 \
  -b "uuid=agent-uuid" \
  -o uncracked_hashes.txt
```

### Get Hash Type

**Endpoint**: `GET /v1/getHashType/<int:hashfile_id>`

**Authorization**: User or Agent

**Description**: Returns the hash type for a specific hashfile.

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "OK",
  "hash_type": 1000
}
```

**Example**:
```bash
curl -X GET http://localhost:5000/v1/getHashType/15 \
  -b "uuid=your-api-key"
```

---

## Hash Management Endpoints

### Upload Cracked Hashes (Legacy)

**Endpoint**: `POST /v1/uploadCrackFile/<int:task_id>/<int:hash_type>`

**Authorization**: Agent only

**Description**: Legacy endpoint for uploading cracked hashes. This is deprecated; use the job_task_id version instead.

**Request Body**:
```json
{
  "file": "hash1:plaintext1\nhash2:plaintext2\n..."
}
```

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "OK"
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/v1/uploadCrackFile/1/1000 \
  -H "Content-Type: application/json" \
  -b "uuid=agent-uuid" \
  -d '{
    "file": "5F4DCC3B5AA765D61D8327DEB882CF99:706173736F7264\n"
  }'
```

### Upload Cracked Hashes

**Endpoint**: `POST /v1/uploadCrackFile/<int:job_task_id>`

**Authorization**: Agent only

**Description**: Uploads cracked hashes from an agent. The system automatically:
- Updates hash records with plaintext
- Sends notifications for watched hashes
- Handles "limit_recovered" job types (stops after first crack)

**Request Body**:
```json
{
  "file": "hash1:plaintext1\nhash2:plaintext2\n..."
}
```

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "OK"
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/v1/uploadCrackFile/123 \
  -H "Content-Type: application/json" \
  -b "uuid=agent-uuid" \
  -d '{
    "file": "5F4DCC3B5AA765D61D8327DEB882CF99:706173736F7264\n"
  }'
```

### Import Cracked Hashes

**Endpoint**: `POST /v1/hashes/import/<int:hash_type>`

**Authorization**: User only

**Description**: Imports previously cracked hashes directly (currently only supports NTLM/1000). The system validates that plaintext correctly decrypts to ciphertext.

**URL Parameters**:
- `hash_type`: Currently only `1000` (NTLM) is supported

**Request Body**: Raw plain text (format: `hash:plaintext`, one per line)

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "OK"
}
```

**Error Response**:
```json
{
  "status": 403,
  "type": "message",
  "msg": "Unsupported Hashtype"
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/v1/hashes/import/1000 \
  -H "Content-Type: text/plain" \
  -b "uuid=your-api-key" \
  --data-binary @cracked_hashes.txt
```

---

## Search Endpoints

### Search for Hash

**Endpoint**: `POST /v1/search`

**Authorization**: User only

**Description**: Searches for a specific hash in the cracked hashes database.

**Request Body**:
```json
{
  "hash": "5F4DCC3B5AA765D61D8327DEB882CF99"
}
```

**Response** (hash found):
```json
{
  "status": 200,
  "type": "message",
  "msg": {
    "hash_type": 1000,
    "hash": "5F4DCC3B5AA765D61D8327DEB882CF99",
    "plaintext": "password"
  }
}
```

**Response** (hash not found):
```json
{
  "status": 200,
  "type": "message",
  "msg": "Search complete. No Results Found."
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/v1/search \
  -H "Content-Type: application/json" \
  -b "uuid=your-api-key" \
  -d '{
    "hash": "5F4DCC3B5AA765D61D8327DEB882CF99"
  }'
```

---

## Error Reporting Endpoints

### Report Error

**Endpoint**: `POST /v1/error`

**Authorization**: Agent only

**Description**: Allows agents to report errors to administrators. Sends email notification to all admin users.

**Request Body**:
```json
{
  "error": "Failed to execute hashcat: invalid hash format"
}
```

**Response**:
```json
{
  "status": 200,
  "type": "message",
  "msg": "OK"
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/v1/error \
  -H "Content-Type: application/json" \
  -b "uuid=agent-uuid" \
  -d '{
    "error": "Hashcat crashed with exit code 255"
  }'
```

---

## Authorization Errors

### Not Authorized

**Endpoint**: `GET /v1/not_authorized` or `POST /v1/not_authorized`

**Description**: Redirected here when authentication fails.

**Response**:
```json
{
  "status": 200,
  "type": "Error",
  "msg": "Your agent is not authorized to work with this cluster."
}
```

### Upgrade Required

**Endpoint**: `GET /v1/upgrade_required`

**Description**: Redirected here when agent version is outdated.

**Response**:
```json
{
  "status": 426,
  "type": "message",
  "msg": "Version missmatch, update your agent!"
}
```

---

## Common Workflow Examples

### Complete Job Workflow

1. **Create a customer** (if needed):
```bash
curl -X POST http://localhost:5000/v1/customers/add \
  -H "Content-Type: application/json" \
  -b "uuid=your-api-key" \
  -d '{"name": "Acme Corp", "description": "Q4 Audit"}'
```

2. **Upload a hashfile**:
```bash
curl -X POST "http://localhost:5000/v1/hashfiles/upload/1/0/1000/DomainHashes" \
  -H "Content-Type: text/plain" \
  -b "uuid=your-api-key" \
  --data-binary @hashes.txt
```

3. **Create a job**:
```bash
curl -X POST http://localhost:5000/v1/jobs/add \
  -H "Content-Type: application/json" \
  -b "uuid=your-api-key" \
  -d '{
    "name": "Q4 Audit Job",
    "hashfile_id": 1,
    "customer_id": 1,
    "limit_recovered": false,
    "notify_email": true
  }'
```

4. **Start the job**:
```bash
curl -X POST http://localhost:5000/v1/jobs/start/1 \
  -b "uuid=your-api-key"
```

### Agent Workflow

1. **Send heartbeat** (agent checks in):
```bash
curl -X POST http://localhost:5000/v1/agents/heartbeat \
  -H "Content-Type: application/json" \
  -b "uuid=agent-uuid; agent_version=0.8.0; name=agent-01" \
  -d '{"agent_status": "Idle", "hc_status": ""}'
```

2. **Get task assignment** (server responds with START message)

3. **Download hashfile**:
```bash
curl -X GET http://localhost:5000/v1/hashfiles/1 \
  -b "uuid=agent-uuid" \
  -o hashes.txt
```

4. **Get task details**:
```bash
curl -X GET http://localhost:5000/v1/tasks/5 \
  -b "uuid=agent-uuid"
```

5. **Update status to working**:
```bash
curl -X POST http://localhost:5000/v1/jobtask/status \
  -H "Content-Type: application/json" \
  -b "uuid=agent-uuid" \
  -d '{"job_task_id": 123, "task_status": "Running"}'
```

6. **Upload cracked hashes**:
```bash
curl -X POST http://localhost:5000/v1/uploadCrackFile/123 \
  -H "Content-Type: application/json" \
  -b "uuid=agent-uuid" \
  -d '{"file": "hash1:plaintext1\nhash2:plaintext2"}'
```

7. **Mark task complete**:
```bash
curl -X POST http://localhost:5000/v1/jobtask/status \
  -H "Content-Type: application/json" \
  -b "uuid=agent-uuid" \
  -d '{"job_task_id": 123, "task_status": "Completed"}'
```

---

## Notes

- All plaintext values in crack files are hex-encoded
- Maximum runtime limits for jobs and tasks are enforced during heartbeat checks
- Hashfile format 22000 (WPA) has special handling in the crack file upload logic
- Dynamic wordlists are automatically updated from the cracked hashes database
- The system uses MD5 sub-ciphertext indexing for faster hash lookups
- Job creation automatically selects the top 10 most effective tasks based on historical success rates for the hash type
