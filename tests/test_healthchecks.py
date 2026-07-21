from django.test import SimpleTestCase, override_settings


@override_settings(ALLOWED_HOSTS=["kaydanshield.com"])
class HealthcheckTests(SimpleTestCase):
    def test_healthz_does_not_access_database(self):
        response = self.client.get(
            "/healthz",
            headers={
                "host": "kaydanshield.com",
                "x-forwarded-proto": "https",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
