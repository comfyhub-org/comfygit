"""Unit tests for input signature normalization."""

from comfygit_core.models.workflow import NodeInput
from comfygit_core.utils.input_signature import (
    create_node_key,
    normalize_registry_inputs,
    normalize_workflow_inputs,
)


class TestInputSignatureNormalization:
    """Test input signature normalization functions."""

    def test_normalize_registry_inputs_basic(self):
        """Test basic registry input normalization."""
        # Test with required inputs including complex types and constraints
        registry_json = '{"required":{"mask":["MASK"],"scale_factor":["FLOAT",{"default":1,"min":0,"max":1,"step":0.01}]}}'

        result = normalize_registry_inputs(registry_json)

        # Should normalize to canonical form: sorted inputs with type only
        assert result == "mask:MASK|scale_factor:FLOAT"

    def test_normalize_workflow_inputs_basic(self):
        """Test basic workflow input normalization from NodeInput objects."""
        # Create NodeInput objects like those parsed from workflow JSON
        workflow_inputs = [
            NodeInput(name="scale_factor", type="FLOAT"),
            NodeInput(name="mask", type="MASK"),
        ]

        result = normalize_workflow_inputs(workflow_inputs)

        # Should produce same canonical form (sorted)
        assert result == "mask:MASK|scale_factor:FLOAT"

    def test_registry_workflow_compatibility(self):
        """Test that equivalent registry and workflow inputs produce identical signatures."""
        # Registry format with complex constraints
        registry_json = '{"required":{"operation":[["some", "values"]],"value":["INT,FLOAT"]}}'

        # Equivalent workflow format
        workflow_inputs = [
            NodeInput(name="value", type="INT,FLOAT"),
            NodeInput(name="operation", type="COMBO"),
        ]

        registry_sig = normalize_registry_inputs(registry_json)
        workflow_sig = normalize_workflow_inputs(workflow_inputs)

        # Both should produce identical canonical signatures
        assert registry_sig == workflow_sig
        assert registry_sig == "operation:COMBO|value:INT,FLOAT"

        # And both should create the same node key
        node_key_registry = create_node_key("UnaryMath", registry_sig)
        node_key_workflow = create_node_key("UnaryMath", workflow_sig)
        assert node_key_registry == node_key_workflow
