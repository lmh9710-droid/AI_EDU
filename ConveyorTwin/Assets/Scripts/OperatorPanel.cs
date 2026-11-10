using UnityEngine;
using UnityEngine.InputSystem;
public class OperatorPanel : MonoBehaviour
{
  
    // Update is called once per frame
    void Update()
    {
        var io = PlcIo.Instance;
        var kb = Keyboard.current;
        if (io == null || kb == null) return;

        // 누르고 있는 동안만 ON (실제 푸시 버튼과 같은 a접점 모멘터리)
        io.X[0] = kb.digit1Key.isPressed; // 1키 = 기동
        io.X[1] = kb.digit2Key.isPressed; // 2키 = 정지

    }
}
