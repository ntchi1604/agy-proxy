import os
import shutil
import tempfile
import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class Patcher:
    """
    Patching mechanisms for agy-proxy:
    - Atomic on-the-fly binary patching (x86-64/ARM64)
    - macOS resign (codesign)
    - JS injections for Eligibility Check bypass
    """

    def __init__(self):
        pass

    def patch_binary(self, binary_path: str, search_bytes: bytes, replace_bytes: bytes) -> bool:
        """
        Atomically replaces `search_bytes` with `replace_bytes` in a given binary.
        Supports any architecture (x86-64/ARM64) assuming correct byte sequences.
        """
        if len(search_bytes) != len(replace_bytes):
            logger.error("Search and replace bytes must be of the same length to preserve offsets.")
            return False

        if not os.path.exists(binary_path):
            logger.error(f"Binary not found: {binary_path}")
            return False

        try:
            # Create temporary file in the same directory for atomic replace across mount points
            dir_name = os.path.dirname(os.path.abspath(binary_path))
            with tempfile.NamedTemporaryFile(dir=dir_name, delete=False) as tmp:
                with open(binary_path, "rb") as f:
                    content = f.read()

                if search_bytes not in content:
                    logger.warning(f"Target bytes not found in binary: {binary_path}")
                    os.unlink(tmp.name)
                    return False

                new_content = content.replace(search_bytes, replace_bytes)
                tmp.write(new_content)
                tmp_name = tmp.name

            # Preserve permissions
            st = os.stat(binary_path)
            os.chmod(tmp_name, st.st_mode)

            # Atomic replace
            os.replace(tmp_name, binary_path)
            logger.info(f"Successfully patched binary: {binary_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to patch binary {binary_path}: {e}")
            return False

    def resign_macos_binary(self, binary_path: str, entitlements_path: Optional[str] = None) -> bool:
        """
        Resigns a macOS binary using codesign.
        """
        if not os.path.exists(binary_path):
            logger.error(f"Binary not found: {binary_path}")
            return False

        try:
            cmd = ["codesign", "-f", "-s", "-"]
            if entitlements_path and os.path.exists(entitlements_path):
                cmd.extend(["--entitlements", entitlements_path])
            cmd.append(binary_path)

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"codesign failed for {binary_path}: {result.stderr}")
                return False

            logger.info(f"Successfully resigned {binary_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to resign binary {binary_path}: {e}")
            return False

    def inject_js(self, html_path: str, js_code: str) -> bool:
        """
        Injects JS for Eligibility Check bypass into a specified HTML file.
        Injections are placed before </head> or </body>.
        """
        if not os.path.exists(html_path):
            logger.error(f"HTML file not found: {html_path}")
            return False

        try:
            dir_name = os.path.dirname(os.path.abspath(html_path))
            with tempfile.NamedTemporaryFile(mode="w", dir=dir_name, delete=False, encoding="utf-8") as tmp:
                with open(html_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                injection = f"\n<script>\n{js_code}\n</script>\n"
                
                if "</head>" in content:
                    new_content = content.replace("</head>", f"{injection}</head>", 1)
                elif "</body>" in content:
                    new_content = content.replace("</body>", f"{injection}</body>", 1)
                else:
                    new_content = content + injection

                tmp.write(new_content)
                tmp_name = tmp.name

            st = os.stat(html_path)
            os.chmod(tmp_name, st.st_mode)

            os.replace(tmp_name, html_path)
            logger.info(f"Successfully injected JS into {html_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to inject JS into {html_path}: {e}")
            return False
