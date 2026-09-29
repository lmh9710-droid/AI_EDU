#pragma once
#include "Common.h"
#include "DatabaseManager.h"

class BaseEquipment {
protected:
    std::string port_path;
    std::string equipment_id;
    std::shared_ptr<DatabaseManager> db_mgr;
    int serial_fd;

    int configureSerial() {
        int fd = open(port_path.c_str(), O_RDWR | O_NOCTTY);
        if (fd < 0) return -1;
        struct termios tty;
        if (tcgetattr(fd, &tty) != 0) return -1;

        cfsetospeed(&tty, B115200);
        cfsetispeed(&tty, B115200);
        tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8; 
        tty.c_lflag = 0; tty.c_oflag = 0; 
        tty.c_iflag &= ~(IXON | IXOFF | IXANY);
        tty.c_cc[VMIN] = 1; tty.c_cc[VTIME] = 1;  
        tty.c_cflag |= (CLOCAL | CREAD); 
        tty.c_cflag &= ~(PARENB | PARODD | CSTOPB | CRTSCTS); 

        if (tcsetattr(fd, TCSANOW, &tty) != 0) return -1;
        return fd;
    }

public:
    BaseEquipment(std::string port, std::string id, std::shared_ptr<DatabaseManager> db)
        : port_path(port), equipment_id(id), db_mgr(db), serial_fd(-1) {}

    virtual ~BaseEquipment() {
        if (serial_fd >= 0) close(serial_fd);
    }

    virtual void startCaptureLoop() = 0; 
};
