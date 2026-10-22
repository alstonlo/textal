"""Public web assets must use the publisher-only pipeline.

This replaces the old CSD CIF/metadata export. See docs/publisher-website.md.
"""

from build_publisher_assets import main

if __name__ == "__main__":
    main()
