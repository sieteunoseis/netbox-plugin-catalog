# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-01-28

### Added

- Initial release
- Plugin catalog browser with filtering and search
- PyPI integration for auto-discovering netbox-* packages
- Curated catalog.json for plugin metadata and compatibility info
- One-click pip install from the UI
- Post-installation instructions with config snippets
- Installation history tracking
- Compatibility detection from:
  - Curated catalog (primary)
  - PluginConfig import (after install)
  - README parsing (fallback)
- REST API for installation logs
- Plugin navigation menu
