# Expected Output

The minimal example returns a close snapshot with `semantic_outputs.final`
coming from the `final` DAG node.

Stable key value:

```python
snapshot["semantic_outputs"]["final"]["task_id"] == "final"
```
