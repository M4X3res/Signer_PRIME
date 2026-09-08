import re

with open('core/final_handler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace print(...) with logger.info/error(...)  
content = re.sub(r'print\(\"(\[FinalHandler\] ERROR.*?)\"', r'logger.error("\1"', content)
content = re.sub(r'print\(f\"(\[FinalHandler\] ERROR.*?)\"', r'logger.error(f"\1"', content)
content = re.sub(r'print\(\"(\[FinalHandler\] ОШИБКА.*?)\"', r'logger.error("\1"', content)
content = re.sub(r'print\(f\"(\[FinalHandler\] ОШИБКА.*?)\"', r'logger.error(f"\1"', content)
content = re.sub(r'print\(f\"(\[FinalHandler\] ВНИМАНИЕ.*?)\"', r'logger.warning(f"\1"', content)

# Replace remaining print(...) with logger.info(...)
content = re.sub(r'print\(\"(\[FinalHandler\].*?)\"', r'logger.info("\1"', content)
content = re.sub(r'print\(f\"(\[FinalHandler\].*?)\"', r'logger.info(f"\1"', content)

with open('core/final_handler.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Replaced print with logger in final_handler.py")
