import pytest
from decimal import Decimal
from core.ecosystem_media import EcosystemImage, MediaKind
from core.leverage_profiles import LeverageProfile, LeverageProfileStore

def test_profiles_are_context_only():
    store=LeverageProfileStore(); profile=LeverageProfile("p1","Nome definido pelo usuário","BRL",Decimal("1000"),Decimal("100")); store.put(profile); assert store.get("p1")==profile
@pytest.mark.parametrize("value",[Decimal("NaN"),Decimal("Infinity"),Decimal("-Infinity"),Decimal("-1")])
def test_profile_rejects_nonfinite_or_negative_risk_budget(value):
    with pytest.raises(ValueError): LeverageProfile("p1","x","BRL",maximum_loss=value).validate()
def test_image_metadata_accepts_safe_supported_type(): EcosystemImage("img1",MediaKind.PROFILE,"image/png",1024,"media/img1.png").validate()
@pytest.mark.parametrize("mime",["image/svg+xml","application/pdf","text/html"])
def test_unsupported_image_types_are_rejected(mime):
    with pytest.raises(ValueError,match="unsupported_image_type"): EcosystemImage("img1",MediaKind.LOGO,mime,1024,"media/img1").validate()
def test_remote_reference_rejected():
    with pytest.raises(ValueError,match="unsafe_storage_reference"): EcosystemImage("img1",MediaKind.BACKGROUND,"image/webp",1024,"https://example.invalid/x.webp").validate()
def test_image_size_bounded():
    with pytest.raises(ValueError,match="image_size_out_of_bounds"): EcosystemImage("img1",MediaKind.PROFILE,"image/jpeg",5*1024*1024+1,"media/img1.jpg").validate()
def test_path_traversal_reference_rejected():
    with pytest.raises(ValueError,match="unsafe_storage_reference"): EcosystemImage("img1",MediaKind.LOGO,"image/png",100,"media/../img.png").validate()


def test_leverage_assessment_never_authorizes_execution():
    from core.leverage_operation import LeverageRequest, assess_leverage
    result = assess_leverage(LeverageRequest("r1","p1","EURUSD",Decimal("2"),Decimal("1000"),Decimal("1"),Decimal("100"),Decimal("1"),Decimal("1"),Decimal("100")))
    assert result.status.value == "acceptable"
    assert result.execution_authorized is False
