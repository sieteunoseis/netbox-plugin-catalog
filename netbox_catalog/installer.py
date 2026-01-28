import logging
import subprocess
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class InstallResult:
    """Result of a pip install operation."""

    success: bool
    package_name: str
    version: str = ""
    output: str = ""
    error: str = ""


class PluginInstaller:
    """Handles pip installation of plugins."""

    def __init__(self, timeout: int = 300):
        self.timeout = timeout

    def install(
        self, package_name: str, version: str = None, upgrade: bool = False
    ) -> InstallResult:
        """Install a package using pip."""
        package_spec = f"{package_name}=={version}" if version else package_name

        cmd = [sys.executable, "-m", "pip", "install"]
        if upgrade:
            cmd.append("--upgrade")
        cmd.append(package_spec)

        try:
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )

            if result.returncode == 0:
                installed_version = self._get_installed_version(package_name)
                return InstallResult(
                    success=True,
                    package_name=package_name,
                    version=installed_version,
                    output=result.stdout,
                )
            else:
                return InstallResult(
                    success=False,
                    package_name=package_name,
                    output=result.stdout,
                    error=result.stderr,
                )

        except subprocess.TimeoutExpired:
            return InstallResult(
                success=False,
                package_name=package_name,
                error=f"Installation timed out after {self.timeout} seconds",
            )
        except Exception as e:
            logger.exception(f"Error installing {package_name}")
            return InstallResult(success=False, package_name=package_name, error=str(e))

    def uninstall(self, package_name: str) -> InstallResult:
        """Uninstall a package using pip."""
        cmd = [sys.executable, "-m", "pip", "uninstall", "-y", package_name]

        try:
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            return InstallResult(
                success=result.returncode == 0,
                package_name=package_name,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else "",
            )

        except Exception as e:
            logger.exception(f"Error uninstalling {package_name}")
            return InstallResult(success=False, package_name=package_name, error=str(e))

    def _get_installed_version(self, package_name: str) -> str:
        """Get the installed version of a package."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", package_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if line.startswith("Version:"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return ""

    def is_installed(self, package_name: str) -> bool:
        """Check if a package is installed."""
        return bool(self._get_installed_version(package_name))

    def generate_config_snippet(self, package_name: str) -> str:
        """Generate the configuration.py snippet for a plugin."""
        module_name = package_name.replace("-", "_")
        return f"""\
# Add to PLUGINS list in configuration.py:
PLUGINS = [
    # ... existing plugins ...
    "{module_name}",
]

# Add plugin configuration (if needed):
PLUGINS_CONFIG = {{
    # ... existing config ...
    "{module_name}": {{
        # Plugin-specific settings here
    }},
}}
"""

    def generate_post_install_commands(self) -> dict:
        """Generate post-installation commands."""
        return {
            "migrate": "python manage.py migrate",
            "collectstatic": "python manage.py collectstatic --no-input",
            "restart_docker": "docker-compose restart netbox",
            "restart_systemd": "sudo systemctl restart netbox",
        }
