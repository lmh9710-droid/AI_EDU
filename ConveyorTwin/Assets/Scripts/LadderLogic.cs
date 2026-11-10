using UnityEngine;

public class LadderLogic : MonoBehaviour
{
    public bool M0;
    private bool prevX3, prevX5;
    // Start is called once before the first execution of Update after the MonoBehaviour is created

    void FixedUpdate()
    {
        var io = PlcIo.Instance;
        if (io == null) return;
        bool[] X = io.X;
        bool[] Y = io.Y;
        short[] D = io.D;

        // 운전 자기유지 LD X0 / OR M0 / ANI X1 / OUT M0
        M0 = (X[0] || M0) && !X[1];

        // 불량 감지 -> 푸셔 전진 LD M0 / AND X2/ SET Y1
        if (M0 && X[2]) Y[1] = true;

        //전진단 도달 -> 후진 LD X5 / RST Y1
        if (X[5]) Y[1] = false;

        //컨베이어 운전 LD M0 / ANI Y1 / AND X4/ OUT Y0

        Y[0] = M0 && !Y[1] && X[4];

        // 양품 카운트 LDP X3 / INC D0
        if (X[3] && !prevX3) D[0]++;

        // 불량 카운트 
        if (X[5] && !prevX5) D[1]++;

        prevX3 = X[3];
        prevX5 = X[5];

       
    }

}
