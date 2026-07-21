from cryptography.fernet import Fernet


def test_follow_up_contact_encrypts_and_masks_phone(monkeypatch):
    from zhenhu.inpatient.services.follow_up_contacts import FollowUpContactService

    monkeypatch.setenv("CONTACT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    service = FollowUpContactService()
    payload = {"mobile_phone": "13800138000", "follow_up_consent": True}

    encrypted = service._encrypt(payload)

    assert "13800138000" not in encrypted
    assert service.summary({**payload, "preferred_channel": "phone"}) == {
        "has_contact": True,
        "follow_up_consent": True,
        "preferred_channel": "phone",
        "masked_mobile_phone": "138****8000",
    }
