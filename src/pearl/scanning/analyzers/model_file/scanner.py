"""Model file security scanner.

Main scanner that orchestrates analysis of model files for security issues.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

from pearl.scanning.types import ScanSeverity

logger = logging.getLogger(__name__)


class ModelFormat(str, Enum):
    """Supported model file formats."""
    PICKLE = "pickle"
    PYTORCH = "pytorch"
    SAFETENSORS = "safetensors"
    GGUF = "gguf"
    ONNX = "onnx"
    TENSORFLOW = "tensorflow"
    KERAS = "keras"
    UNKNOWN = "unknown"


class FindingCategory(str, Enum):
    """Categories of model file security findings."""
    CODE_EXECUTION = "code_execution"
    MALICIOUS_PAYLOAD = "malicious_payload"
    UNSAFE_DESERIALIZATION = "unsafe_deserialization"
    SUPPLY_CHAIN = "supply_chain"
    FORMAT_VIOLATION = "format_violation"
    SUSPICIOUS_CONTENT = "suspicious_content"


@dataclass
class ModelFileFinding:
    """A security finding in a model file."""
    category: FindingCategory
    severity: ScanSeverity
    title: str
    description: str
    file_path: Path
    location: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "file_path": str(self.file_path),
            "location": self.location,
            "evidence": self.evidence,
            "remediation": self.remediation,
        }


@dataclass
class ModelFileResult:
    """Result of scanning a model file."""
    file_path: Path
    file_size: int
    file_hash: str
    format: ModelFormat
    findings: list[ModelFileFinding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        """Check if no security issues were found."""
        return len(self.findings) == 0

    @property
    def critical_count(self) -> int:
        """Count of critical findings."""
        return sum(1 for f in self.findings if f.severity == ScanSeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        """Count of high severity findings."""
        return sum(1 for f in self.findings if f.severity == ScanSeverity.HIGH)

    def findings_by_severity(self, severity: ScanSeverity) -> list[ModelFileFinding]:
        """Get findings filtered by severity."""
        return [f for f in self.findings if f.severity == severity]


# File extension to format mapping
FORMAT_EXTENSIONS: dict[str, ModelFormat] = {
    ".pkl": ModelFormat.PICKLE,
    ".pickle": ModelFormat.PICKLE,
    ".pt": ModelFormat.PYTORCH,
    ".pth": ModelFormat.PYTORCH,
    ".bin": ModelFormat.PYTORCH,  # Can also be safetensors
    ".safetensors": ModelFormat.SAFETENSORS,
    ".gguf": ModelFormat.GGUF,
    ".onnx": ModelFormat.ONNX,
    ".pb": ModelFormat.TENSORFLOW,
    ".h5": ModelFormat.KERAS,
    ".keras": ModelFormat.KERAS,
}


class ModelFileScanner:
    """Scanner for detecting security issues in model files.

    Analyzes model files for:
    - Pickle deserialization attacks
    - Malicious code embedded in PyTorch models
    - Format-specific vulnerabilities
    - Supply chain issues (hash verification, provenance)
    """

    def __init__(
        self,
        check_pickle: bool = True,
        check_pytorch: bool = True,
        check_safetensors: bool = True,
        check_gguf: bool = True,
        check_supply_chain: bool = True,
        trusted_sources: list[str] | None = None,
    ):
        """Initialize model file scanner.

        Args:
            check_pickle: Enable pickle exploit detection.
            check_pytorch: Enable PyTorch malware detection.
            check_safetensors: Enable safetensors validation.
            check_gguf: Enable GGUF validation.
            check_supply_chain: Enable supply chain verification.
            trusted_sources: List of trusted model sources/hubs.
        """
        self.check_pickle = check_pickle
        self.check_pytorch = check_pytorch
        self.check_safetensors = check_safetensors
        self.check_gguf = check_gguf
        self.check_supply_chain = check_supply_chain
        self.trusted_sources = trusted_sources or [
            "huggingface.co",
            "pytorch.org",
            "tensorflow.org",
        ]

    def detect_format(self, file_path: Path) -> ModelFormat:
        """Detect model file format.

        Args:
            file_path: Path to the model file.

        Returns:
            Detected model format.
        """
        suffix = file_path.suffix.lower()

        # Check extension first
        if suffix in FORMAT_EXTENSIONS:
            # Special case: .bin could be PyTorch or safetensors
            if suffix == ".bin":
                return self._detect_bin_format(file_path)
            return FORMAT_EXTENSIONS[suffix]

        # Try to detect from content
        return self._detect_from_content(file_path)

    def _detect_bin_format(self, file_path: Path) -> ModelFormat:
        """Detect format of .bin files."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(8)

            # Safetensors starts with JSON header size
            if len(header) >= 8:
                # Check if it looks like safetensors (little-endian u64 header size)
                header_size = int.from_bytes(header[:8], "little")
                if 0 < header_size < 100_000_000:  # Reasonable header size
                    return ModelFormat.SAFETENSORS

            return ModelFormat.PYTORCH
        except Exception:
            return ModelFormat.UNKNOWN

    def _detect_from_content(self, file_path: Path) -> ModelFormat:
        """Detect format from file content."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(16)

            # Check magic bytes
            if header.startswith(b"GGUF"):
                return ModelFormat.GGUF
            if header.startswith(b"\x80\x04\x95"):  # Pickle protocol 4
                return ModelFormat.PICKLE
            if header.startswith(b"\x80\x05\x95"):  # Pickle protocol 5
                return ModelFormat.PICKLE

            return ModelFormat.UNKNOWN
        except Exception:
            return ModelFormat.UNKNOWN

    def compute_hash(self, file_path: Path, algorithm: str = "sha256") -> str:
        """Compute file hash.

        Args:
            file_path: Path to the file.
            algorithm: Hash algorithm (sha256, sha1, md5).

        Returns:
            Hex digest of the hash.
        """
        hasher = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def scan_file(self, file_path: Path | str) -> ModelFileResult:
        """Scan a single model file for security issues.

        Args:
            file_path: Path to the model file.

        Returns:
            ModelFileResult with findings.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return ModelFileResult(
                file_path=file_path,
                file_size=0,
                file_hash="",
                format=ModelFormat.UNKNOWN,
                errors=[f"File not found: {file_path}"],
            )

        # Get file info
        file_size = file_path.stat().st_size
        file_hash = self.compute_hash(file_path)
        model_format = self.detect_format(file_path)

        result = ModelFileResult(
            file_path=file_path,
            file_size=file_size,
            file_hash=file_hash,
            format=model_format,
            metadata={
                "extension": file_path.suffix,
                "name": file_path.name,
            },
        )

        # Run format-specific analyzers
        try:
            findings = list(self._analyze_file(file_path, model_format))
            result.findings.extend(findings)
        except Exception as e:
            result.errors.append(f"Analysis error: {e}")
            logger.exception(f"Error analyzing {file_path}")

        # Basic supply chain check (no external dependency)
        if self.check_supply_chain:
            # Check if file came from known source
            result.metadata["file_hash"] = file_hash
            result.metadata["verified"] = False  # No provenance info available in static scan

        return result

    def _analyze_file(self, file_path: Path, model_format: ModelFormat) -> Iterator[ModelFileFinding]:
        """Analyze file based on format with inline checks."""
        # Pickle/PyTorch: always flag pickle-based formats as risky
        if model_format in (ModelFormat.PICKLE, ModelFormat.PYTORCH):
            yield ModelFileFinding(
                category=FindingCategory.UNSAFE_DESERIALIZATION,
                severity=ScanSeverity.CRITICAL,
                title=f"Pickle-based model format: {model_format.value}",
                description="Pickle deserialization can execute arbitrary code. This model format is inherently unsafe unless loaded in a sandboxed environment.",
                file_path=file_path,
                remediation="Convert to SafeTensors format or verify model provenance before loading.",
            )
            # Check for suspicious pickle opcodes
            try:
                with open(file_path, "rb") as f:
                    header = f.read(4096)
                dangerous_opcodes = [b"__reduce__", b"__reduce_ex__", b"os.system", b"subprocess", b"eval(", b"exec("]
                for opcode in dangerous_opcodes:
                    if opcode in header:
                        yield ModelFileFinding(
                            category=FindingCategory.MALICIOUS_PAYLOAD,
                            severity=ScanSeverity.CRITICAL,
                            title=f"Suspicious content in model file: {opcode.decode(errors='replace')}",
                            description="Model file header contains content associated with code execution payloads.",
                            file_path=file_path,
                            evidence={"opcode": opcode.decode(errors="replace")},
                            remediation="Do not load this model. Scan with dedicated malware analysis tools.",
                        )
            except Exception:
                pass

        # GGUF: check for valid header
        if model_format == ModelFormat.GGUF:
            try:
                with open(file_path, "rb") as f:
                    magic = f.read(4)
                if magic != b"GGUF":
                    yield ModelFileFinding(
                        category=FindingCategory.FORMAT_VIOLATION,
                        severity=ScanSeverity.MEDIUM,
                        title="Invalid GGUF header",
                        description="File claims to be GGUF but has invalid magic bytes.",
                        file_path=file_path,
                        remediation="Verify file integrity and re-download from trusted source.",
                    )
            except Exception:
                pass

        # SafeTensors: generally safe but check header
        if model_format == ModelFormat.SAFETENSORS:
            try:
                with open(file_path, "rb") as f:
                    header_size_bytes = f.read(8)
                if len(header_size_bytes) == 8:
                    header_size = int.from_bytes(header_size_bytes, "little")
                    if header_size > 100_000_000:
                        yield ModelFileFinding(
                            category=FindingCategory.SUSPICIOUS_CONTENT,
                            severity=ScanSeverity.MEDIUM,
                            title="Unusually large SafeTensors header",
                            description=f"Header size ({header_size} bytes) is suspiciously large.",
                            file_path=file_path,
                            remediation="Verify file integrity.",
                        )
            except Exception:
                pass

    def scan_directory(
        self,
        directory: Path | str,
        recursive: bool = True,
    ) -> list[ModelFileResult]:
        """Scan a directory for model files.

        Args:
            directory: Directory to scan.
            recursive: Scan subdirectories.

        Returns:
            List of results for each model file found.
        """
        directory = Path(directory)
        results = []

        # Find model files
        pattern = "**/*" if recursive else "*"
        for file_path in directory.glob(pattern):
            if file_path.is_file() and self._is_model_file(file_path):
                result = self.scan_file(file_path)
                results.append(result)

        return results

    def _is_model_file(self, file_path: Path) -> bool:
        """Check if file is a model file.

        Args:
            file_path: Path to check.

        Returns:
            True if file appears to be a model file.
        """
        suffix = file_path.suffix.lower()
        return suffix in FORMAT_EXTENSIONS or self.detect_format(file_path) != ModelFormat.UNKNOWN

    def to_analyzer_result(self, results: list[ModelFileResult]):
        """Convert model file results to standard AnalyzerResult."""
        from pearl.scanning.analyzers.base import AnalyzerFinding, AnalyzerResult as AR
        from pearl.scanning.types import AttackCategory, ComponentType

        findings = []
        cat_map = {
            FindingCategory.CODE_EXECUTION: AttackCategory.SUPPLY_CHAIN,
            FindingCategory.MALICIOUS_PAYLOAD: AttackCategory.SUPPLY_CHAIN,
            FindingCategory.UNSAFE_DESERIALIZATION: AttackCategory.SUPPLY_CHAIN,
            FindingCategory.SUPPLY_CHAIN: AttackCategory.SUPPLY_CHAIN,
            FindingCategory.FORMAT_VIOLATION: AttackCategory.SUPPLY_CHAIN,
            FindingCategory.SUSPICIOUS_CONTENT: AttackCategory.DATA_MODEL_POISONING,
        }
        for result in results:
            for f in result.findings:
                findings.append(AnalyzerFinding(
                    title=f.title,
                    description=f.description,
                    severity=f.severity,
                    category=cat_map.get(f.category, AttackCategory.SUPPLY_CHAIN),
                    component_type=ComponentType.MODEL,
                    component_name=str(result.file_path.name),
                    file_path=str(f.file_path),
                    evidence=[{"type": "model_file", "format": result.format.value, "file_hash": result.file_hash, "file_size": result.file_size}],
                    remediation_summary=f.remediation,
                    confidence=0.9,
                    tags=["model_file", f.category.value, result.format.value],
                ))
        return AR(
            analyzer_name="model_file",
            findings=findings,
            metadata={"files_scanned": len(results)},
        )
