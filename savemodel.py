from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "distilgpt2"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

# Save to a directory
output_dir = "./distilgpt2-model"
tokenizer.save_pretrained(output_dir)
model.save_pretrained(output_dir)