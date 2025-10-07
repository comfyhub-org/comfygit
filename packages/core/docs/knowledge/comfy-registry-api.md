# Comfy API Endpoints Reference

**Base URL:** `https://api.comfy.org`

## User Management

### Users
- `GET /users` - Get information about the calling user

## CI/CD Data

### Git Commits
- `GET /gitcommit` - Retrieve CI data for a given commit
- `GET /gitcommitsummary` - Retrieve a summary of git commits

### Workflow Results
- `GET /workflowresult/{workflowResultId}` - Retrieve a specific workflow result by ID
- `POST /upload-artifact` - Receive artifacts from ComfyUI GitHub Action

### Branches
- `GET /branch` - Retrieve all distinct branches for a repository

## Publishers

### Publisher Management
- `GET /publishers` - Retrieve all publishers
- `POST /publishers` - Create a new publisher
- `GET /publishers/{publisherId}` - Retrieve a publisher by ID
- `PUT /publishers/{publisherId}` - Update a publisher
- `DELETE /publishers/{publisherId}` - Delete a publisher
- `POST /publishers/{publisherId}/ban` - Ban a publisher

### Publisher Validation & Permissions
- `GET /publishers/validate` - Validate if a publisher username is available
- `GET /users/publishers/` - Retrieve all publishers for the current user
- `GET /publishers/{publisherId}/permissions` - Get user permissions for a publisher

### Personal Access Tokens
- `POST /publishers/{publisherId}/tokens` - Create a new personal access token
- `GET /publishers/{publisherId}/tokens` - List all personal access tokens for a publisher
- `DELETE /publishers/{publisherId}/tokens/{tokenId}` - Delete a specific personal access token

## Nodes

### Node Management
- `GET /nodes` - Retrieve a paginated list of all nodes
- `GET /nodes/search` - Search nodes with keyword filtering
- `GET /nodes/{nodeId}` - Retrieve a specific node by ID
- `POST /nodes/reindex` - Reindex all nodes for searching

### Publisher Node Management
- `POST /publishers/{publisherId}/nodes` - Create a new custom node
- `GET /publishers/{publisherId}/nodes` - Retrieve all nodes for a publisher
- `PUT /publishers/{publisherId}/nodes/{nodeId}` - Update a specific node
- `DELETE /publishers/{publisherId}/nodes/{nodeId}` - Delete a specific node
- `POST /publishers/{publisherId}/nodes/{nodeId}/ban` - Ban a publisher's node
- `GET /publishers/{publisherId}/nodes/{nodeId}/permissions` - Get user permissions for a node

### Node Installation & Reviews
- `GET /nodes/{nodeId}/install` - Get node version for installation
- `POST /nodes/{nodeId}/reviews` - Add a review to a node

## Node Versions

### Version Management
- `GET /nodes/{nodeId}/versions` - List all versions of a node
- `GET /nodes/{nodeId}/versions/{versionId}` - Retrieve a specific version of a node
- `GET /versions` - List all node versions with filters
- `POST /publishers/{publisherId}/nodes/{nodeId}/versions` - Publish a new version of a node
- `PUT /publishers/{publisherId}/nodes/{nodeId}/versions/{versionId}` - Update version changelog and deprecation
- `DELETE /publishers/{publisherId}/nodes/{nodeId}/versions/{versionId}` - Unpublish a version

### Admin Version Management
- `PUT /admin/nodes/{nodeId}/versions/{versionNumber}` - Admin update node version status

## ComfyUI Nodes

### ComfyUI Node Management
- `POST /nodes/{nodeId}/versions/{version}/comfy-nodes` - Create comfy-nodes for a node version
- `GET /nodes/{nodeId}/versions/{version}/comfy-nodes/{comfyNodeId}` - Get specific comfy-node by ID
- `POST /comfy-nodes/backfill` - Trigger comfy nodes backfill

## Security & Administration

### Security Scanning
- `GET /security-scan` - Pull and scan pending node versions for security issues

## Authentication

Most endpoints require Bearer token authentication. Include the token in the Authorization header:
```
Authorization: Bearer <your-token>
```

## Response Formats

All endpoints return JSON responses with appropriate HTTP status codes:
- `200` - Success
- `201` - Created
- `204` - Success (No Content)
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `500` - Internal Server Error

## Query Parameters

Many endpoints support pagination and filtering:
- `page` - Page number (default: 1)
- `limit`/`pageSize` - Items per page (default: 10)
- `include_banned` - Include banned items (boolean)
- `search` - Keyword search
- `timestamp` - Filter by creation/update time
- `latest` - Fetch fresh results vs cached (boolean)