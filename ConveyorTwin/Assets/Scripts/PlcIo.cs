using UnityEngine;

public class PlcIo : MonoBehaviour
{
    public static PlcIo Instance;

    public bool[] X = new bool[16]; // 입력(설비 -> PLC) 
    public bool[] Y = new bool[16]; // 출력(PLC -> 설비)
    public short[] D = new short[16]; // 데이터 레지스터

    void Awake()
    {
        Instance = this;
    }
}
