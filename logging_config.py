import logging

# Cấu hình logging
logging.basicConfig(
    filename='app.log',            # Tên file log
    filemode='w',                  # Chế độ 'w' để ghi đè vào file, hoặc 'w' để ghi đè
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Định dạng log
    level=logging.DEBUG            # Mức độ log cần ghi (DEBUG, INFO, WARNING, ERROR, CRITICAL)
)