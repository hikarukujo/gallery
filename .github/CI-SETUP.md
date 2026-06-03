# Gallery CI → ACR setup

`build-and-deploy.yml` mirrors the other apps (e.g. roleplai-cx): on push to `main` it
logs in to Azure with **Entra OIDC** (no stored client secret), pushes
`azacr1.azurecr.io/gallery:<sha>` + `:latest`, then bumps the `build-sha` annotation in
`platform-infra/apps/gallery/deployment.yaml` so Argo CD re-pulls the new image.

It reuses the **same** identity wiring your other app repos use:

| Name | Type | Used for |
|------|------|----------|
| `AZURE_CLIENT_ID` | variable (`vars.`) | Entra app (client) ID for OIDC login |
| `AZURE_TENANT_ID` | variable | Entra tenant |
| `AZURE_SUBSCRIPTION_ID` | variable | subscription |
| `PLATFORM_INFRA_PAT` | secret | push the build-sha bump to `hikarukujo/platform-infra` |

## 1. Variables / secret

If these are defined at the **org** level, `hikarukujo/gallery` already inherits them —
confirm:

```bash
gh variable list -R hikarukujo/gallery     # expect AZURE_CLIENT_ID / TENANT_ID / SUBSCRIPTION_ID
gh secret   list -R hikarukujo/gallery     # expect PLATFORM_INFRA_PAT
```

If any are missing (repo-scoped setup), set them:

```bash
gh variable set AZURE_CLIENT_ID       -R hikarukujo/gallery -b "<client-id>"
gh variable set AZURE_TENANT_ID       -R hikarukujo/gallery -b "<tenant-id>"
gh variable set AZURE_SUBSCRIPTION_ID -R hikarukujo/gallery -b "<subscription-id>"
gh secret   set PLATFORM_INFRA_PAT    -R hikarukujo/gallery -b "<pat>"
# PAT: fine-grained, Contents: Read/Write on hikarukujo/platform-infra
```

## 2. The one genuinely new thing — a federated credential for this repo

Entra OIDC trust is scoped per repo + ref, so add a federated credential for
`hikarukujo/gallery` to the **existing** CI Entra app (the one behind
`vars.AZURE_CLIENT_ID`). Reusing that app means its existing `AcrPush` role on `azacr1`
already applies — nothing else to grant:

```bash
az ad app federated-credential create \
  --id "<AZURE_CLIENT_ID>" \
  --parameters '{
    "name": "github-gallery-main",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:hikarukujo/gallery:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'
```

The subject matches the workflow — it only logs in to Azure on push to `main`, not on PRs.

> If your apps instead use **one Entra app per repo**, create a new app registration, set
> the three repo `vars` to its IDs, add the same federated credential, and grant it push:
> `az role assignment create --assignee <appId> --role AcrPush --scope $(az acr show -n azacr1 --query id -o tsv)`

## 3. Verify

Push a commit (or use **Actions → Build and Deploy → Run workflow**). Expected:
the `build` job pushes the image; `bump-platform-infra` lands a
`gallery: rolled to build <sha>` commit on platform-infra; Argo rolls the pod.
