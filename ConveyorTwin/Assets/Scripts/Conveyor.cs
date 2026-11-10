using Unity.Collections;
using UnityEngine;
using UnityEngine.InputSystem;

public class Conveyor : MonoBehaviour
{
    public float speed = 0.5f; //벨트 속도(m/s)
    public bool isRunning = false;
    public int yNo = 0; // 구동 출력 번호 

    private Rigidbody body;

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        body = GetComponent<Rigidbody>();
    }

    // Update is called once per frame
    void Update()
    {
        isRunning = PlcIo.Instance != null && PlcIo.Instance.Y[yNo];
        // 스페이스바를 누를 때마다 켜고 끄기 
        if (Keyboard.current != null && Keyboard.current.spaceKey.wasPressedThisFrame)
        {
            isRunning = !isRunning;
            Debug.Log("컨베이어" + (isRunning ? "ON" : "OFF"));
        }
    }

    void FixedUpdate()
    {
        if (!isRunning) return;
        //벨트를 뒤로 살짝 옮겼다가 제자리로 "움직여" 돌아오게 함 
        // -> 위에 놓인 물체가 마찰 때문에 앞으로 끌려감
        Vector3 pos = body.position;
        body.position = pos - transform.right * speed * Time.fixedDeltaTime;
        body.MovePosition(pos);
     
     }
}


