# ComfyHub Documentation Hub

This repository hosts the GitHub Pages site for ComfyHub documentation at `docs.comfyhub.org`.

## Structure

```
comfyhub-org.github.io/
├── CNAME                    # Custom domain: docs.comfyhub.org
├── index.html               # Hub landing page
├── comfygit/                # ComfyGit documentation (deployed from monorepo)
│   ├── index.html
│   ├── getting-started/
│   ├── user-guide/
│   └── ...
└── comfydock/               # Legacy comfydock documentation (future)
    └── ...
```

## Deployments

### ComfyGit Documentation

Deployed automatically from the monorepo via GitHub Actions:
- Source: `comfyhub-org/comfygit` → `docs/comfydock-docs/`
- Workflow: `.github/workflows/publish-docs.yml`
- Target: `/comfygit/` subdirectory in this repo
- Trigger: Manual via GitHub Actions

### Legacy comfydock Documentation

To be added later for archival purposes.

## Custom Domain Setup

**Domain:** docs.comfyhub.org

**DNS Configuration:**
- Type: CNAME
- Name: docs
- Target: comfyhub-org.github.io.
- TTL: 3600

**GitHub Pages Configuration:**
1. Repository Settings → Pages
2. Source: Deploy from branch `main` / `/ (root)`
3. Custom domain: `docs.comfyhub.org`
4. Enforce HTTPS: ✅

## Hub Landing Page

The `index.html` at the root provides navigation to all project documentation:
- Clean, modern design
- Links to `/comfygit/` (current)
- Links to `/comfydock/` (legacy)
- Responsive and accessible

## Manual Deployment (if needed)

Normally deployments happen automatically via GitHub Actions, but you can manually deploy:

```bash
# Clone this repo
git clone https://github.com/comfyhub-org/comfyhub-org.github.io.git
cd comfyhub-org.github.io

# Make changes
# ... edit files ...

# Commit and push
git add .
git commit -m "Update documentation"
git push
```

GitHub Pages will rebuild automatically (usually within 1-2 minutes).

## Important Files

- **CNAME**: Must remain at root for custom domain to work
- **index.html**: Hub landing page, manually maintained
- **comfygit/**: Auto-deployed, DO NOT manually edit
- **comfydock/**: To be added for legacy docs

## Troubleshooting

### Site not updating
- Wait 1-2 minutes for GitHub Pages rebuild
- Check Actions tab for build status
- Clear browser cache (Ctrl+Shift+R)

### Custom domain not working
- Verify DNS CNAME record: `dig docs.comfyhub.org`
- Check GitHub Pages settings show custom domain
- Wait up to 24 hours for DNS propagation

### 404 errors on subpaths
- Ensure directory structure is correct
- Check that `comfygit/index.html` exists
- Verify MkDocs built with correct `site_url`

## Links

- **Live Site**: https://docs.comfyhub.org
- **ComfyGit Repo**: https://github.com/comfyhub-org/comfygit
- **Organization**: https://github.com/comfyhub-org
