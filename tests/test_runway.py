import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from glass_fruit.config import load_config
from glass_fruit.generate import campaign, generate_mock, generate_live
from glass_fruit.runway import Ledger, RunwayClient, RunwayError

ROOT = Path(__file__).resolve().parents[1]


def response(value):
    return io.BytesIO(json.dumps(value).encode())


class RunwayTransportTests(unittest.TestCase):
    def test_default_gate_does_not_send_even_get(self):
        opener = Mock()
        with self.assertRaises(RunwayError):
            RunwayClient('secret', opener=opener).request('POST', '/v1/text_to_video', {})
        opener.assert_not_called()

    def test_post_timeout_never_retried(self):
        opener = Mock(side_effect=TimeoutError())
        with self.assertRaises(RunwayError):
            RunwayClient('secret', allow_paid=True, opener=opener).create('video', {})
        self.assertEqual(opener.call_count, 1)

    def test_get_retry_and_contract_headers(self):
        opener = Mock(side_effect=[urllib.error.HTTPError('url', 429, 'rate', {'Retry-After': '2'}, None),
                                  response({'id': 'task1', 'status': 'SUCCEEDED', 'output': ['https://example.test/a.mp4']})])
        sleep = Mock()
        result = RunwayClient('secret', allow_paid=True, opener=opener, sleep=sleep).wait('task1')
        self.assertEqual(result['status'], 'SUCCEEDED')
        sleep.assert_called_once_with(2)
        request = opener.call_args.args[0]
        self.assertEqual(request.get_header('X-runway-version'), '2024-11-06')

    def test_auth_error_no_retry_and_no_secret_or_response_in_error(self):
        opener = Mock(side_effect=urllib.error.HTTPError('url', 401, 'secret server text', {}, None))
        with self.assertRaises(RunwayError) as caught:
            RunwayClient('secret-key', allow_paid=True, opener=opener).wait('task1')
        self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(opener.call_count, 1)

    def test_failed_task_is_not_regenerated(self):
        opener = Mock(return_value=response({'status': 'FAILED'}))
        with self.assertRaises(RunwayError):
            RunwayClient('secret', allow_paid=True, opener=opener).wait('task1')
        self.assertEqual(opener.call_count, 1)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'ledger.sqlite'
        self.ledger = Ledger(self.path)
        self.addCleanup(self.ledger.close)
        self.job = dict(key='stable', cents=120, kind='video', payload={'model': 'gen4.5'})

    def test_budget_exact_ceiling_and_atomic_overflow(self):
        self.assertEqual(self.ledger.reserve([dict(self.job, cents=1000)]), 1000)
        with self.assertRaises(RunwayError):
            self.ledger.reserve([dict(self.job, key='extra', cents=1)])
        self.assertIsNone(self.ledger.row('extra'))

    def test_unknown_price_and_changed_price_block(self):
        with self.assertRaises(RunwayError):
            self.ledger.reserve([dict(self.job, cents=None)])
        self.ledger.reserve([self.job])
        with self.assertRaises(RunwayError):
            self.ledger.reserve([dict(self.job, cents=10)])

    def test_resume_retains_task_and_never_resubmits(self):
        client = Mock(); client.create.return_value = 'task1'
        self.ledger.reserve([self.job])
        self.assertEqual(self.ledger.submit(self.job, client), 'task1')
        resumed = Ledger(self.path)
        try:
            resumed.reserve([self.job])
            self.assertEqual(resumed.submit(self.job, client), 'task1')
        finally:
            resumed.close()
        self.assertEqual(client.create.call_count, 1)

    def test_lost_post_response_reservation_is_not_released(self):
        self.ledger.reserve([self.job])
        client = Mock(); client.create.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            self.ledger.submit(self.job, client)
        with self.assertRaises(RunwayError):
            self.ledger.submit(self.job, client)
        self.assertEqual(client.create.call_count, 1)
        with self.assertRaises(RunwayError):
            self.ledger.reserve([dict(self.job, key='extra', cents=881)])

    def test_plan_unknown_price_and_over_budget(self):
        cfg = load_config(ROOT / 'configs/shorts-seven.yaml')
        plan = campaign(cfg)
        self.assertEqual(len(plan['jobs']), 14)
        self.assertEqual(plan['status'], 'price-review-required')
        self.assertFalse(plan['live_enabled'])
        self.assertEqual(campaign(cfg, 120, 30)['status'], 'over-budget')
        for job in plan['jobs']:
            self.assertEqual(job['payload']['duration'], 10)


class OfflineMockIntegrationTests(unittest.TestCase):
    def test_70s_mock_resume_and_tamper_detection_without_network(self):
        cfg = load_config(ROOT / 'configs/shorts-seven.yaml')
        cfg['video'].update(width=180, height=320)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'campaign'
            with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')):
                first = generate_mock(cfg, folder)
                resumed = generate_mock(cfg, folder)
                self.assertEqual(first['duration_seconds'], 70)
                self.assertEqual(first['new_mock_submissions'], 14)
                self.assertEqual(resumed['new_mock_submissions'], 0)
                self.assertEqual(resumed['actual_api_cost_cents'], 0)
                self.assertEqual(resumed['simulated_reserved_cents'], 910)
                media = next(p for p in folder.glob('*.wav'))
                media.write_bytes(b'corrupted')
                with self.assertRaisesRegex(RunwayError, 'integrity'):
                    generate_mock(cfg, folder)

    def test_create_uses_official_endpoints_and_camelcase_payload(self):
        client = RunwayClient('test-secret', allow_paid=True,
                              opener=Mock(return_value=response({'id': 'task1'})))
        cfg = load_config(ROOT / 'configs/shorts-seven.yaml')
        for kind in ('video', 'audio'):
            job = next(j for j in campaign(cfg)['jobs'] if j['kind'] == kind)
            client.opener.return_value = response({'id': 'task1'})
            self.assertEqual(client.create(kind, job['payload']), 'task1')
            request = client.opener.call_args.args[0]
            body = json.loads(request.data)
            self.assertIn('promptText', body)
            self.assertEqual(body['duration'], 10)
            self.assertTrue(request.full_url.endswith('/text_to_video' if kind == 'video' else '/sound_effect'))


class LiveBoundaryTests(unittest.TestCase):
    def test_production_requires_all_reviews_before_any_request(self):
        client = Mock(allow_paid=True)
        cfg = load_config(ROOT / 'configs/shorts-seven.yaml')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RunwayError):
                generate_live(cfg, tmp, client, video_cents=120, sound_cents=10)
            with self.assertRaises(RunwayError):
                generate_live(cfg, tmp, client, video_cents=120, sound_cents=30,
                              user_approved=True, pricing_verified=True, account_cap_verified=True)
        client.create.assert_not_called()

    def test_output_download_does_not_forward_api_secret_and_retries(self):
        opener = Mock(side_effect=[TimeoutError(), io.BytesIO(b'pretend media')])
        client = RunwayClient('never-leak-this', allow_paid=True, opener=opener, sleep=Mock())
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'video.mp4'
            client.download('https://media.example.test/output.mp4?temporary=signature', target)
            self.assertEqual(target.read_bytes(), b'pretend media')
        self.assertEqual(opener.call_count, 2)
        for call in opener.call_args_list:
            self.assertFalse(call.args[0].has_header('Authorization'))
        with self.assertRaises(RunwayError):
            client.download('http://media.example.test/insecure', Path('/tmp/unused'))
