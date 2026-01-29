# NetBox Plugin Catalog

A NetBox plugin that provides an in-app catalog for browsing and installing third-party NetBox plugins.

![NetBox Version](https://img.shields.io/badge/NetBox-4.0+-blue)
![Python Version](https://img.shields.io/badge/Python-3.10+-green)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/sieteunoseis/netbox-plugin-catalog/actions/workflows/ci.yml/badge.svg)](https://github.com/sieteunoseis/netbox-plugin-catalog/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/netbox-plugin-catalog)](https://pypi.org/project/netbox-plugin-catalog/)

## Features

- **Browse Plugins**: Discover NetBox plugins from PyPI with rich metadata
- **Curated Catalog**: Quality ratings, categories, and compatibility information
- **One-Click Install**: Install plugins directly from the NetBox UI via pip
- **Compatibility Checking**: Verify plugin compatibility with your NetBox version
- **Installation History**: Track all plugin installation attempts
- **Smart Detection**: Auto-detect installed and activated plugins

## Requirements

- NetBox 4.0.0 or higher
- Python 3.10 or higher

## Installation

### Via pip

```bash
pip install netbox-plugin-catalog
```

### Via source

```bash
git clone https://github.com/sieteunoseis/netbox-plugin-catalog.git
cd netbox-plugin-catalog
pip install .
```

## Configuration

Add the plugin to your `configuration.py`:

```python
PLUGINS = [
    'netbox_catalog',
]

PLUGINS_CONFIG = {
    'netbox_catalog': {
        'pypi_cache_timeout': 3600,        # Cache PyPI data for 1 hour
        'catalog_json_url': '',            # Optional: remote catalog.json URL
        'allow_install': True,             # Enable/disable pip install feature
        'show_uncurated': True,            # Show plugins not in curated list
        'pypi_index_url': 'https://pypi.org',  # PyPI mirror support
    }
}
```

Run migrations:

```bash
python manage.py migrate
```

Collect static files:

```bash
python manage.py collectstatic --no-input
```

Restart NetBox.

## Usage

### Browsing Plugins

Navigate to **Plugins > Plugin Catalog > Browse Plugins** to view all available NetBox plugins.

You can filter by:
- **Search**: Filter by name, summary, or author
- **Category**: Network Management, Security, Automation, etc.
- **Certification**: Certified, Compatible, Untested, Deprecated
- **Status**: Installed, Not Installed, Activated, Upgrade Available
- **Compatibility**: Compatible, Incompatible, Unknown

### Installing Plugins

1. Click on a plugin to view details
2. Click **Install** (or **Upgrade** if already installed)
3. Confirm the installation
4. Follow the post-installation instructions:
   - Add the plugin to `PLUGINS` in `configuration.py`
   - Run `python manage.py migrate`
   - Run `python manage.py collectstatic`
   - Restart NetBox

### Compatibility Detection

The plugin checks compatibility through multiple sources:

1. **Curated catalog**: Manually verified compatibility info in `catalog.json`
2. **PluginConfig**: After pip install, reads `min_version`/`max_version` from plugin
3. **README parsing**: Attempts to extract version info from description (fallback)

Compatibility status is shown with clear indicators:
- **Compatible**: Plugin works with your NetBox version
- **Unknown**: No compatibility information available
- **Incompatible**: Plugin requires a different NetBox version

## Curated Catalog

The `catalog.json` file provides curated metadata for plugins:

```json
{
    "plugins": {
        "netbox-bgp": {
            "category": "Network Management",
            "tags": ["routing", "bgp"],
            "certification": "certified",
            "netbox_min_version": "4.0.0",
            "notes": "Official BGP plugin",
            "recommended": true,
            "featured": true
        }
    }
}
```

### Updating the Catalog

You can host your own catalog JSON and configure it:

```python
PLUGINS_CONFIG = {
    'netbox_catalog': {
        'catalog_json_url': 'https://example.com/netbox-plugins.json',
    }
}
```

## Docker Installation

For Docker deployments, the plugin can automatically add packages to `requirements-extra.txt` instead of using pip directly. This allows installations to persist across container restarts.

### Setup

1. **Mount requirements-extra.txt as read-write** in your `docker-compose.yml`:

```yaml
services:
  netbox:
    volumes:
      - ./requirements-extra.txt:/opt/netbox/requirements-extra.txt:rw
```

2. **Set file permissions** so the NetBox process can write to it:

```bash
# The NetBox container runs the web process as 'unit' user (UID 999)
# The file needs to be writable by this user
chmod 666 ./requirements-extra.txt
```

3. **Restart the container** to apply the volume mount changes.

### How It Works

When properly configured:
1. Click **Add to Requirements** on a plugin's install page
2. The package spec is appended to `requirements-extra.txt`
3. Edit `configuration/plugins.py` to add the plugin to `PLUGINS`
4. Restart the container: `docker-compose down && docker-compose up -d`
5. The container startup script installs packages from `requirements-extra.txt`

### Troubleshooting

If you see **"Manual Installation Required"** instead of the install button:

- Verify `requirements-extra.txt` is mounted with `:rw` (not `:ro`)
- Check file permissions: `ls -la requirements-extra.txt`
- Ensure the file exists (create an empty one if needed)

## Security Considerations

- **Permissions**: Only users with `netbox_catalog.add_installationlog` permission can install plugins
- **pip install**: Runs in the same Python environment as NetBox
- **Docker**: Writes to requirements-extra.txt, which is installed on container restart
- **Network access**: Requires outbound HTTPS to pypi.org

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

### Adding Plugins to Curated Catalog

To add a plugin to the curated catalog, submit a PR updating `catalog.json` with:

- `category`: One of the predefined categories
- `tags`: Relevant keywords
- `certification`: certified, compatible, untested, or deprecated
- `netbox_min_version`: Minimum supported NetBox version
- `notes`: Brief description or compatibility notes
- `recommended`: Whether the plugin is recommended
- `featured`: Whether to show in featured section

## License

Apache License 2.0

## Acknowledgments

- [NetBox](https://github.com/netbox-community/netbox) - The leading network source of truth
- [NetBox Labs](https://netboxlabs.com/plugins/) - Plugin catalog inspiration
- All the NetBox plugin developers
