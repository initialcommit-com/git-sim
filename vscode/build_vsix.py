"""Package the extension as a .vsix without Node: the same layout vsce produces
(a zip with a manifest, content types and the extension folder).

    python build_vsix.py            -> git-sim-<version>.vsix beside this file
"""

import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
FILES = [
    "package.json",
    "extension.js",
    "README.md",
    "CHANGELOG.md",
    "LICENSE.txt",
    "media/icon.png",
    "media/live.svg",
]
CONTENT_TYPES = {
    ".json": "application/json",
    ".js": "application/javascript",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".vsixmanifest": "text/xml",
}


def manifest(pkg):
    props = {
        "Microsoft.VisualStudio.Code.Engine": pkg["engines"]["vscode"],
        "Microsoft.VisualStudio.Code.ExtensionDependencies": "",
        "Microsoft.VisualStudio.Code.ExtensionPack": "",
        "Microsoft.VisualStudio.Code.ExtensionKind": "workspace",
        "Microsoft.VisualStudio.Code.LocalizedLanguages": "",
        "Microsoft.VisualStudio.Services.Links.Source": pkg["repository"]["url"],
        "Microsoft.VisualStudio.Services.Links.Getstarted": pkg["repository"]["url"],
        "Microsoft.VisualStudio.Services.Links.Support": pkg["bugs"]["url"],
        "Microsoft.VisualStudio.Services.Links.Learn": pkg["homepage"],
        "Microsoft.VisualStudio.Services.Branding.Color": "#fff7ed",
        "Microsoft.VisualStudio.Services.Branding.Theme": "light",
    }
    properties = "".join(
        f'<Property Id="{k}" Value="{escape(v, {chr(34): "&quot;"})}"/>'
        for k, v in props.items()
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{pkg['name']}" Version="{pkg['version']}" Publisher="{pkg['publisher']}"/>
    <DisplayName>{escape(pkg['displayName'])}</DisplayName>
    <Description xml:space="preserve">{escape(pkg['description'])}</Description>
    <Tags>{escape(",".join(pkg.get("keywords", [])))}</Tags>
    <Categories>{escape(",".join(pkg.get("categories", [])))}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>{properties}</Properties>
    <License>extension/LICENSE.txt</License>
    <Icon>extension/media/icon.png</Icon>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Content.Changelog" Path="extension/CHANGELOG.md" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE.txt" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Icons.Default" Path="extension/media/icon.png" Addressable="true"/>
  </Assets>
</PackageManifest>
"""


def content_types():
    defaults = "".join(
        f'<Default Extension="{ext}" ContentType="{ct}"/>'
        for ext, ct in CONTENT_TYPES.items()
    )
    return f'<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">{defaults}</Types>'


def main():
    pkg = json.loads((HERE / "package.json").read_text(encoding="utf-8"))
    if not (
        HERE / "LICENSE.txt"
    ).exists():  # the repo's licence, named the way the manifest expects
        (HERE / "LICENSE.txt").write_bytes((HERE.parent / "LICENSE").read_bytes())
    target = HERE / f"{pkg['name']}-{pkg['version']}.vsix"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("extension.vsixmanifest", manifest(pkg))
        z.writestr("[Content_Types].xml", content_types())
        for rel in FILES:
            z.write(HERE / rel, f"extension/{rel}")
    print(target)


if __name__ == "__main__":
    sys.exit(main())
