"""
Проверка размера входа ONNX модели.
"""
import onnx

onnx_path = "CNN_side/best.onnx"
model = onnx.load(onnx_path)

print("=== ONNX Model Input Info ===")
for input_tensor in model.graph.input:
    print(f"Name: {input_tensor.name}")
    print(f"Type: {input_tensor.type}")
    shape = input_tensor.type.tensor_type.shape
    print(f"Shape: ", end="")
    for dim in shape.dim:
        if dim.dim_value:
            print(f"{dim.dim_value}", end=" ")
        else:
            print(f"{dim.dim_param}", end=" ")
    print()
