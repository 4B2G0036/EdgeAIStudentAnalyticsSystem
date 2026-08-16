# testcam.py
import cv2
from core.camera import CameraManager
import cv2
from core.camera import CameraManager

def main():
    print("啟動情緒分析系統...")
    
    # 建立相機管理器實例
    cam = CameraManager()
    
    try:
        cam.connect()
        print("相機連線成功，準備讀取畫面。")
        
        # 這裡會放入你之後處理多重人臉偵測與情緒辨識的迴圈
        while True:
            ret, frame = cam.read_frame()
            if not ret:
                break
                
            # 顯示畫面測試
            cv2.imshow("Emotion Detection System", frame)
            
            # 按下 'q' 鍵離開
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    except Exception as e:
        print(f"系統發生錯誤: {e}")
    finally:
        cam.disconnect()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()