# Setting Up the GitHub Pages Hub Repository

Follow these steps to initialize the `comfyhub-org/comfyhub-org.github.io` repository.

## Step 1: Clone the Repository

```bash
cd ~/projects/comfydock/  # or wherever you keep repos
git clone https://github.com/comfyhub-org/comfyhub-org.github.io.git
cd comfyhub-org.github.io
```

## Step 2: Copy Hub Infrastructure Files

From the monorepo, copy the hub infrastructure files:

```bash
# From within comfyhub-org.github.io directory
cp ../comfygit/docs/hub-infrastructure/index.html .
cp ../comfygit/docs/hub-infrastructure/CNAME .
cp ../comfygit/docs/hub-infrastructure/README.md .
```

## Step 3: Create Initial Directory Structure

```bash
# Create placeholder for comfygit docs (will be populated by workflow)
mkdir -p comfygit
echo "# ComfyGit Documentation\n\nThis directory is auto-deployed from the monorepo.\nDo not manually edit files here." > comfygit/README.md

# Create placeholder for legacy comfydock docs (future)
mkdir -p comfydock
echo "# Legacy comfydock Documentation\n\nTo be added." > comfydock/README.md
```

## Step 4: Commit and Push

```bash
git add .
git commit -m "Initialize ComfyHub documentation hub

- Add hub landing page (index.html)
- Configure custom domain (CNAME)
- Create directory structure for multi-project docs
- Add README with setup instructions"

git push origin main
```

## Step 5: Configure GitHub Pages

1. Go to: https://github.com/comfyhub-org/comfyhub-org.github.io/settings/pages
2. **Source**: Deploy from a branch
3. **Branch**: `main`
4. **Folder**: `/ (root)`
5. **Custom domain**: `docs.comfyhub.org`
6. Click **Save**
7. Wait for DNS check to complete (may take a few minutes)
8. Once verified, check **Enforce HTTPS**

## Step 6: Verify Deployment

Wait 1-2 minutes for GitHub Pages to build, then visit:
- https://docs.comfyhub.org (should show hub landing page)
- https://comfyhub-org.github.io (should redirect to custom domain)

## Step 7: Test Token Access

Verify the deployment workflow can push to this repo:

```bash
# From the monorepo
cd ~/projects/comfyhub/comfygit

# Check that DOCS_PUBLISH_TOKEN secret exists and has correct permissions
gh secret list --repo comfyhub-org/comfygit
# Should show: DOCS_PUBLISH_TOKEN

# Test token can access the Pages repo (if you have gh cli configured)
gh api repos/comfyhub-org/comfyhub-org.github.io
# Should return repo info without error
```

If the token doesn't exist or doesn't have access:

1. Create a new Personal Access Token:
   - Go to: https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Name: "ComfyHub Docs Publishing"
   - Scopes: `repo` (full control)
   - Generate and copy the token

2. Add as secret to monorepo:
   - Go to: https://github.com/comfyhub-org/comfygit/settings/secrets/actions
   - Click "New repository secret"
   - Name: `DOCS_PUBLISH_TOKEN`
   - Value: (paste token)
   - Add secret

## Step 8: Ready for First Deployment

Once the hub is set up and token is configured, you can deploy ComfyGit docs:

```bash
# From monorepo
cd ~/projects/comfyhub/comfygit

# Trigger the workflow (after it's been updated)
gh workflow run publish-docs.yml --repo comfyhub-org/comfygit

# Or trigger via GitHub UI:
# https://github.com/comfyhub-org/comfygit/actions/workflows/publish-docs.yml
```

## Verification Checklist

- [ ] DNS resolves: `dig docs.comfyhub.org` shows CNAME
- [ ] Hub repo exists: https://github.com/comfyhub-org/comfyhub-org.github.io
- [ ] Hub landing page deployed: https://docs.comfyhub.org
- [ ] GitHub Pages configured with custom domain
- [ ] HTTPS enforced
- [ ] DOCS_PUBLISH_TOKEN secret exists in monorepo
- [ ] Token has write access to hub repo
- [ ] Ready for first docs deployment

## Next Steps

Once hub is verified working:
1. Update monorepo docs configuration (mkdocs.yml)
2. Update deployment workflow for subpath deployment
3. Run first deployment to populate `/comfygit/`
4. Verify docs appear at https://docs.comfyhub.org/comfygit/
