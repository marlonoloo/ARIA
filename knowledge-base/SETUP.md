# Bedrock Knowledge Base (RAG) Setup

This sets up the retrieval half of the two Lambdas. The Knowledge Base stores
clinical protocols as vectors so Claude's briefings/diagnoses are *grounded*
rather than free-form.

> All steps assume `us-east-1` (best Bedrock model availability). Use ReadOnly
> creds for inspection; only the create steps below need write access. This is a
> PoC — prefer the console wizard, it provisions the OpenSearch collection for you.

## 0. Request model access (one-time)

Bedrock console → **Model access** → enable:
- **Anthropic Claude 3 Sonnet** (generation)
- **Amazon Titan Text Embeddings V2** (vectorisation)

Access can take a few minutes to activate.

## 1. Upload the protocol docs to S3

```bash
# Pick a unique bucket name.
aws s3 mb s3://aria-kb-protocols-<your-suffix> --region us-east-1

aws s3 cp knowledge-base/protocols/ \
  s3://aria-kb-protocols-<your-suffix>/protocols/ \
  --recursive --region us-east-1
```

## 2. Create the Knowledge Base (console wizard — fastest)

Bedrock console → **Knowledge Bases** → **Create**:
1. Data source: **S3**, point at `s3://aria-kb-protocols-<your-suffix>/protocols/`.
2. Embeddings model: **Titan Text Embeddings V2**.
3. Vector store: **Quick create a new vector store** → Amazon OpenSearch
   Serverless (the wizard creates the collection + index + IAM for you).
4. Create, then open the data source and click **Sync**. Re-sync whenever you
   change a protocol doc — this is the "swap a PDF, change the AI" story.

Copy the **Knowledge Base ID** (e.g. `ABCD1234`) — it becomes `KB_ID`.

## 3. Verify retrieval before wiring the Lambdas

```bash
aws bedrock-agent-runtime retrieve \
  --knowledge-base-id <KB_ID> \
  --retrieval-query '{"text":"pregnant patient with vaginal bleeding"}' \
  --region us-east-1
```

You should get back passages from the WHO triage excerpt. If you get zero
results, the data source has not finished syncing.

## 4. Lambda environment variables

Both functions need:

| Variable | Example | Notes |
|----------|---------|-------|
| `KB_ID` | `ABCD1234` | from step 2 |
| `DB_CLUSTER_ARN` | `arn:aws:rds:us-east-1:...:cluster:aria` | Aurora cluster ARN |
| `DB_SECRET_ARN` | `arn:aws:secretsmanager:...` | cluster's managed secret |
| `DB_NAME` | `aria` | defaults to `aria` |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-sonnet-20240229-v1:0` | default |
| `KB_NUM_RESULTS` | `5` | optional |
| `LOG_LEVEL` | `INFO` | optional |

## 5. IAM permissions the Lambda execution role needs

Least-privilege starter policy (scope the resources to your ARNs):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockRetrieve",
      "Effect": "Allow",
      "Action": "bedrock:Retrieve",
      "Resource": "arn:aws:bedrock:us-east-1:<acct>:knowledge-base/<KB_ID>"
    },
    {
      "Sid": "BedrockInvoke",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0"
    },
    {
      "Sid": "AuroraDataApi",
      "Effect": "Allow",
      "Action": [
        "rds-data:ExecuteStatement"
      ],
      "Resource": "arn:aws:rds:us-east-1:<acct>:cluster:<cluster-id>"
    },
    {
      "Sid": "ReadDbSecret",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "<DB_SECRET_ARN>"
    }
  ]
}
```

Also enable the **RDS Data API** on the Aurora cluster (RDS console → cluster →
Modify → enable Data API, or `aws rds modify-db-cluster --enable-http-endpoint`).
