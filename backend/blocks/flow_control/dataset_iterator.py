"""Dataset iterator block — drives batch execution from a CSV file."""

from __future__ import annotations

from blocks.base import BlockBase, PortDefinition, ParameterDefinition


class DatasetIterator(BlockBase):
    """Reads a CSV file row by row and drives one full downstream execution per row.

    This block is handled specially by the executor: run() is never called.
    Instead, the executor detects this block (via is_iterator = True), reads
    the CSV, and loops over rows — injecting column values as synthetic output
    port values for each iteration.

    Output ports are dynamic: one port per entry in column_mappings.  The
    static class definition declares outputs = [] because the actual ports
    depend on the column_mappings parameter set at design time.
    """

    is_iterator: bool = True   # signals special executor handling

    block_type_id = "dataset_iterator"
    display_name  = "Dataset iterator"
    category      = "Flow control"
    description   = (
        "Reads a CSV file row by row. On each iteration outputs the values "
        "from the selected columns as string ports. Drives one full execution "
        "of all downstream blocks per row."
    )

    inputs     = []
    outputs    = []   # dynamic — resolved from column_mappings at runtime
    parameters = [
        ParameterDefinition(
            name="csv_path",
            data_type="str",
            default="",
            description="Path to the dataset CSV file.",
        ),
        ParameterDefinition(
            name="column_mappings",
            data_type="str",
            default="",
            description=(
                'JSON mapping output port names to CSV column names. '
                'E.g. {"lfp_path": "lfp_file", "spikes_path": "spikes_file"}'
            ),
        ),
        ParameterDefinition(
            name="skip_header",
            data_type="bool",
            default=True,
            description="Whether the first row is a header row.",
        ),
        ParameterDefinition(
            name="session_id_col",
            data_type="str",
            default="",
            description="Optional column name to use as the session label in logs.",
        ),
    ]

    def run(self, inputs: dict, parameters: dict) -> dict:  # pragma: no cover
        raise NotImplementedError(
            "dataset_iterator is handled by the execution engine and should "
            "never be called via run()."
        )
