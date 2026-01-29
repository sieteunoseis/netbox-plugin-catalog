import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

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

    REQUIREMENTS_FILE = "/opt/netbox/requirements-extra.txt"

    def __init__(self, timeout: int = 300):
        self.timeout = timeout
        self._pip_cmd = None

    def _find_pip(self) -> list:
        """Find the best way to invoke pip."""
        if self._pip_cmd:
            return self._pip_cmd

        # Try various methods to find pip
        candidates = []

        # Method 1: pip in the same directory as the Python executable
        python_dir = Path(sys.executable).parent
        pip_path = python_dir / "pip"
        if pip_path.exists():
            candidates.append([str(pip_path)])

        pip3_path = python_dir / "pip3"
        if pip3_path.exists():
            candidates.append([str(pip3_path)])

        # Method 2: python -m pip
        candidates.append([sys.executable, "-m", "pip"])

        # Method 3: pip from PATH
        pip_from_path = shutil.which("pip")
        if pip_from_path:
            candidates.append([pip_from_path])

        pip3_from_path = shutil.which("pip3")
        if pip3_from_path:
            candidates.append([pip3_from_path])

        # Test each candidate
        for cmd in candidates:
            try:
                result = subprocess.run(
                    cmd + ["--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self._pip_cmd = cmd
                    logger.info(f"Found working pip command: {' '.join(cmd)}")
                    return cmd
            except Exception:
                continue

        # Default to python -m pip even if it might fail
        return [sys.executable, "-m", "pip"]

    def is_pip_available(self) -> bool:
        """Check if pip is available."""
        cmd = self._find_pip()
        try:
            result = subprocess.run(
                cmd + ["--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def is_docker_environment(self) -> bool:
        """Check if running in a Docker container."""
        # Check for Docker-specific files
        if Path("/.dockerenv").exists():
            return True
        # Check cgroup (common Docker indicator)
        try:
            with open("/proc/1/cgroup", "r") as f:
                return "docker" in f.read()
        except Exception:
            pass
        return os.environ.get("NETBOX_DOCKER") == "true"

    def is_requirements_file_writable(self) -> bool:
        """Check if requirements-extra.txt is writable."""
        req_path = Path(self.REQUIREMENTS_FILE)
        if not req_path.exists():
            return False
        return os.access(req_path, os.W_OK)

    def get_requirements_packages(self) -> dict[str, str]:
        """Get packages from requirements-extra.txt as {name: spec}."""
        packages = {}
        req_path = Path(self.REQUIREMENTS_FILE)
        if not req_path.exists():
            return packages

        try:
            with open(req_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Parse package spec (e.g., "package>=1.0.0" or "package")
                    for sep in [">=", "<=", "==", "!=", ">", "<", "~="]:
                        if sep in line:
                            name = line.split(sep)[0].strip()
                            packages[name] = line
                            break
                    else:
                        packages[line] = line
        except Exception as e:
            logger.error(f"Error reading requirements file: {e}")

        return packages

    def add_to_requirements(
        self, package_name: str, version: str = None
    ) -> InstallResult:
        """Add a package to requirements-extra.txt for Docker installations."""
        if not self.is_requirements_file_writable():
            return InstallResult(
                success=False,
                package_name=package_name,
                error="requirements-extra.txt is not writable. Check Docker volume mount.",
            )

        # Build package spec
        package_spec = f"{package_name}>={version}" if version else package_name

        # Check if already present
        existing = self.get_requirements_packages()
        if package_name in existing:
            # Update the existing entry
            old_spec = existing[package_name]
            if old_spec == package_spec:
                return InstallResult(
                    success=True,
                    package_name=package_name,
                    version=version or "",
                    output=f"Package already in requirements: {package_spec}",
                )
            # Replace the old spec with new one
            try:
                req_path = Path(self.REQUIREMENTS_FILE)
                content = req_path.read_text()
                content = content.replace(old_spec, package_spec)
                req_path.write_text(content)
                logger.info(
                    f"Updated {old_spec} to {package_spec} in requirements-extra.txt"
                )
                return InstallResult(
                    success=True,
                    package_name=package_name,
                    version=version or "",
                    output=f"Updated package in requirements: {package_spec}",
                )
            except Exception as e:
                logger.exception(f"Error updating requirements file")
                return InstallResult(
                    success=False,
                    package_name=package_name,
                    error=str(e),
                )

        # Append new package
        try:
            with open(self.REQUIREMENTS_FILE, "a") as f:
                f.write(f"{package_spec}\n")
            logger.info(f"Added {package_spec} to requirements-extra.txt")
            return InstallResult(
                success=True,
                package_name=package_name,
                version=version or "",
                output=f"Added to requirements-extra.txt: {package_spec}",
            )
        except Exception as e:
            logger.exception(f"Error writing to requirements file")
            return InstallResult(
                success=False,
                package_name=package_name,
                error=str(e),
            )

    def remove_from_requirements(self, package_name: str) -> InstallResult:
        """Remove a package from requirements-extra.txt."""
        if not self.is_requirements_file_writable():
            return InstallResult(
                success=False,
                package_name=package_name,
                error="requirements-extra.txt is not writable.",
            )

        existing = self.get_requirements_packages()
        if package_name not in existing:
            return InstallResult(
                success=True,
                package_name=package_name,
                output="Package not in requirements file.",
            )

        try:
            req_path = Path(self.REQUIREMENTS_FILE)
            lines = req_path.read_text().splitlines()
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    # Check if this line is for our package
                    line_pkg = stripped.split(">=")[0].split("<=")[0].split("==")[0]
                    line_pkg = (
                        line_pkg.split(">")[0].split("<")[0].split("~=")[0].strip()
                    )
                    if line_pkg == package_name:
                        continue
                new_lines.append(line)

            req_path.write_text("\n".join(new_lines) + "\n")
            logger.info(f"Removed {package_name} from requirements-extra.txt")
            return InstallResult(
                success=True,
                package_name=package_name,
                output=f"Removed from requirements-extra.txt: {package_name}",
            )
        except Exception as e:
            logger.exception(f"Error removing from requirements file")
            return InstallResult(
                success=False,
                package_name=package_name,
                error=str(e),
            )

    def install(
        self, package_name: str, version: str = None, upgrade: bool = False
    ) -> InstallResult:
        """Install a package using pip."""
        # Check if pip is available
        if not self.is_pip_available():
            docker_msg = ""
            if self.is_docker_environment():
                docker_msg = (
                    "\n\nThis NetBox instance is running in Docker. "
                    "To install plugins in Docker:\n"
                    "1. Add the package to requirements-extra.txt\n"
                    "2. Restart the NetBox container\n\n"
                    "See the plugin detail page for manual installation instructions."
                )
            return InstallResult(
                success=False,
                package_name=package_name,
                error=f"pip is not available in this environment.{docker_msg}",
            )

        package_spec = f"{package_name}=={version}" if version else package_name

        cmd = self._find_pip() + ["install"]
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
        if not self.is_pip_available():
            return InstallResult(
                success=False,
                package_name=package_name,
                error="pip is not available in this environment.",
            )

        cmd = self._find_pip() + ["uninstall", "-y", package_name]

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
            cmd = self._find_pip() + ["show", package_name]
            result = subprocess.run(
                cmd,
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
