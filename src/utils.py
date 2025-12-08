import pandas as pd

def read_last_csv_line(filepath):
    """Read the last line of a CSV file efficiently."""
    with open(filepath, 'rb') as f:
        # Go to the end of the file
        f.seek(0, 2)
        file_size = f.tell()
        
        # Start from the end and read backwards
        buffer_size = 8192
        position = file_size
        lines = []
        
        while position > 0:
            # Move back by buffer_size or to start of file
            position = max(0, position - buffer_size)
            f.seek(position)
            chunk = f.read(min(buffer_size, file_size - position))
            lines = chunk.split(b'\n')
            
            # If we found at least 2 lines (last might be empty), we're done
            if len(lines) > 1 and lines[-1] == b'':
                return lines[-2].decode('utf-8')
            elif len(lines) > 0 and lines[-1] != b'':
                return lines[-1].decode('utf-8')
        
        return lines[0].decode('utf-8') if lines else ''
    
def extract_last(data, timedelta):
    # print(data)
    # print(data['time'])
    # print('LAST ELEMENT', data['time'].iloc[-1])
    last_24h = pd.to_datetime(data['time'].iloc[-1], utc=True) - timedelta
    data24h = data.copy()
    data24h['time'] = pd.to_datetime(data24h['time'], utc=True)
    data24h = data24h[data24h['time'] >= last_24h]
    return data24h