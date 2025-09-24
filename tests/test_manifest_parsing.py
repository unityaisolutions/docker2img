import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from docker_registry import DockerRegistryClient  # noqa: E402


class ManifestParsingTests(unittest.TestCase):
    """Unit tests for manifest parsing logic that do not rely on network access."""

    def setUp(self):
        dxf_patcher = patch('docker_registry.DXF')
        self.addCleanup(dxf_patcher.stop)
        self.mock_dxf_cls = dxf_patcher.start()

        self.mock_dxf = MagicMock()
        self.mock_dxf_cls.return_value = self.mock_dxf

        self.client = DockerRegistryClient('registry-1.docker.io', 'library/test')

    def test_platform_dict_manifest_selects_requested_platform(self):
        """DXF returning a platform keyed dict should resolve to the requested platform."""

        amd64_manifest = {
            'schemaVersion': 2,
            'mediaType': 'application/vnd.oci.image.manifest.v1+json',
            'layers': [{'digest': 'sha256:layer-amd64'}],
        }
        arm_manifest = {
            'schemaVersion': 2,
            'mediaType': 'application/vnd.oci.image.manifest.v1+json',
            'layers': [{'digest': 'sha256:layer-arm64'}],
        }

        self.mock_dxf.get_manifest.return_value = {
            'linux/amd64': json.dumps(amd64_manifest),
            'linux/arm64/v8': json.dumps(arm_manifest),
        }

        manifest = self.client.get_manifest('latest', platform='linux/amd64')

        self.assertEqual(manifest['schemaVersion'], 2)
        self.assertEqual(manifest['mediaType'], 'application/vnd.oci.image.manifest.v1+json')
        self.assertEqual(
            [layer['digest'] for layer in manifest['layers']],
            ['sha256:layer-amd64'],
        )

    def test_manifest_list_fetches_platform_digest(self):
        """Manifest lists should resolve to the correct platform digest."""

        manifest_digest = 'sha256:platform'

        manifest_list = {
            'schemaVersion': 2,
            'mediaType': 'application/vnd.docker.distribution.manifest.list.v2+json',
            'manifests': [
                {
                    'digest': manifest_digest,
                    'mediaType': 'application/vnd.docker.distribution.manifest.v2+json',
                    'platform': {'os': 'linux', 'architecture': 'amd64'},
                }
            ],
        }

        platform_manifest = {
            'schemaVersion': 2,
            'mediaType': 'application/vnd.docker.distribution.manifest.v2+json',
            'layers': [{'digest': 'sha256:layer-platform'}],
        }

        def get_manifest_side_effect(tag, platform=None):
            if tag == 'latest':
                return manifest_list
            if tag == manifest_digest:
                self.assertEqual(platform, 'linux/amd64')
                return json.dumps(platform_manifest)
            raise AssertionError(f'Unexpected call get_manifest({tag}, {platform})')

        self.mock_dxf.get_manifest.side_effect = get_manifest_side_effect

        manifest = self.client.get_manifest('latest', platform='linux/amd64')

        self.assertEqual(manifest['schemaVersion'], 2)
        self.assertEqual(
            [layer['digest'] for layer in manifest['layers']],
            ['sha256:layer-platform'],
        )

    def test_falls_back_to_first_platform_if_requested_missing(self):
        """When requested platform missing, resolver should fall back to first entry."""

        fallback_manifest = {
            'schemaVersion': 2,
            'mediaType': 'application/vnd.oci.image.manifest.v1+json',
            'layers': [{'digest': 'sha256:fallback'}],
        }

        self.mock_dxf.get_manifest.return_value = {
            'linux/arm64/v8': json.dumps(fallback_manifest),
        }

        manifest = self.client.get_manifest('latest', platform='linux/amd64')

        self.assertEqual(
            [layer['digest'] for layer in manifest['layers']],
            ['sha256:fallback'],
        )


if __name__ == '__main__':
    unittest.main()