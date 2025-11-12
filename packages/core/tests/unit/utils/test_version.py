"""Tests for version.py utilities."""

from comfygit_core.utils.version import (
    get_pytorch_index_url,
    is_pytorch_package,
    normalize_package_name,
)


class TestIsPytorchPackage:
    def test_core_pytorch_packages(self):
        assert is_pytorch_package("torch")
        assert is_pytorch_package("torchvision")
        assert is_pytorch_package("torchaudio")
        assert is_pytorch_package("torchtext")

    def test_nvidia_cuda_packages(self):
        assert is_pytorch_package("nvidia-cuda-runtime-cu12")
        assert is_pytorch_package("nvidia-cublas-cu11")
        assert is_pytorch_package("nvidia-cudnn-cu12")

    def test_non_pytorch_packages(self):
        assert not is_pytorch_package("numpy")
        assert not is_pytorch_package("requests")
        assert not is_pytorch_package("pillow")

    def test_case_insensitive(self):
        assert is_pytorch_package("TORCH")
        assert is_pytorch_package("TorchVision")
        assert is_pytorch_package("NVIDIA-CUDA-RUNTIME-CU12")

    def test_nvidia_packages_without_cuda(self):
        # NVIDIA packages without cu11/cu12 are not PyTorch-related
        assert not is_pytorch_package("nvidia-ml-py")
        assert not is_pytorch_package("nvidia-gpu-driver")

    def test_edge_cases(self):
        assert not is_pytorch_package("")
        assert not is_pytorch_package("pytorch")  # Not in the explicit set
        assert is_pytorch_package("triton")  # Should be in constants

    def test_custom_pytorch_packages_set(self):
        custom_set = {"custom-torch", "special-gpu"}
        assert is_pytorch_package("custom-torch", custom_set)
        assert not is_pytorch_package("torch", custom_set)


class TestGetPytorchIndexUrl:
    def test_cpu_version(self):
        url = get_pytorch_index_url("2.0.0+cpu")
        assert url == "https://download.pytorch.org/whl/cpu"

    def test_cuda_version(self):
        url = get_pytorch_index_url("2.0.0+cu118")
        assert url == "https://download.pytorch.org/whl/cu118"

    def test_cuda_nightly_version(self):
        url = get_pytorch_index_url("2.1.0.dev20230815+cu118")
        assert url == "https://download.pytorch.org/whl/nightly/cu118"

    def test_fallback_to_cuda_version(self):
        url = get_pytorch_index_url("2.0.0", cuda_torch_version="12.1")
        assert url == "https://download.pytorch.org/whl/cu121"

    def test_fallback_to_cuda_nightly(self):
        url = get_pytorch_index_url("2.1.0.dev20230815", cuda_torch_version="11.8")
        assert url == "https://download.pytorch.org/whl/nightly/cu118"

    def test_no_version_info(self):
        url = get_pytorch_index_url("2.0.0")
        assert url == "https://download.pytorch.org/whl/cpu"

    def test_empty_version(self):
        url = get_pytorch_index_url("")
        assert url is None

    def test_none_version(self):
        url = get_pytorch_index_url(None)
        assert url is None


class TestNormalizePackageName:
    def test_simple_package(self):
        assert normalize_package_name("numpy") == "numpy"

    def test_uppercase_package(self):
        assert normalize_package_name("TORCH") == "torch"

    def test_package_with_extras(self):
        assert normalize_package_name("torch[cuda]") == "torch"
        assert normalize_package_name("tensorflow[gpu]") == "tensorflow"

    def test_package_with_spaces(self):
        assert normalize_package_name("  torch  ") == "torch"
        assert normalize_package_name("  torch[cuda]  ") == "torch"

    def test_complex_extras(self):
        assert normalize_package_name("package[extra1,extra2]") == "package"

    def test_empty_string(self):
        assert normalize_package_name("") == ""

    def test_only_brackets(self):
        assert normalize_package_name("[extra]") == ""
