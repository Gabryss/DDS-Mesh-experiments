import psutil
import csv
import os
import time
import argparse
import serial
import subprocess
from config import Config


class Monitoring:

    def __init__(self, experiment_name_p, experiment_duration_p=30, experiment_timestep_p=0.1, is_target_p=0):
        """
        Defaults attributes of the monitoring class are:
        - Experiment duration : 30 seconds
        - Experiment timestep : 10 Hz (0.1 second)
        """
        self.starting_time = int(round(time.time() * 1000))
        self.experiment_name = experiment_name_p+"_global_monitoring"
        self.experiment_duration = float(experiment_duration_p)
        self.experiment_timestep = float(experiment_timestep_p)
        self.database_path = Config.DATASET_PATH.value
        self.is_target = is_target_p
        self.table_row = ["Timestamp", "Bytes_Send", "Bytes_Received", "Packets_Send", "Packets_Received", "Errors_Send", "Errors_Received", "Drop_Incoming", "Drop_total", "CPU_percent", "CPU_time", "RAM_percent", "RAM_info"]
        if not self.is_target:
            self.table_row.append("Ping_target")
        if self.get_gps_data:
            self.table_row += ["LAT", "LONG", "ALT"]
        self.data = []
        self.old_network_data = None
        self.new_network_data = None
        self.gps_data = [0.0, 0.0, 0.0]


        # GPS
        self.serial_location = '/dev/gps'
        self.serial_baudrate = 9600
        self.serial_timeout = 5



        self.create_csv(self.experiment_name)
        self.get_data()
        
        #Quit the NMEA connection
        exit()


    def check_dataset_directory(self):
        """
        Check if the dataset directory exist
        If not, create it
        """
        if not os.path.exists(self.database_path):
            os.makedirs(self.database_path)


    def create_csv(self, experiment_name_p):
        """
        Create the csv file with the correct fields for the given experiment (name_p)
        """
        self.check_dataset_directory()
        with open(f"{self.database_path}/{experiment_name_p}.csv", 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(self.table_row)


    def write_csv(self, force_p=False):
        """
        Add data to the already created csv file
        Return an error if the file was not created
        """
        #Checks
        self.check_dataset_directory()
        path = f"{self.database_path}/{self.experiment_name}.csv"

        if os.path.isfile(path) or force_p:
            with open(path, 'a',  encoding='UTF8', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(self.data)
        else:
            raise Exception('The csv file was not created, please create it first')
        

    def cpu_measure(self):
        """
        Measure the cpu usage (percentage) of ROS 2 node
        """
        processes = []
        for proc in psutil.process_iter():
            if proc.name() == "ros2":
                processes.append(proc)
    
        cpu_percent = 0
        cpu_time = 0
        
        for proc in processes:
            cpu_percent += proc.cpu_percent(interval=0.2)
            cpu_time += sum(proc.cpu_times()[:2])
        return cpu_percent, cpu_time
        

    def ram_measure(self):
        """
        Measure the ram usage () of ROS 2 node
        """
        processes = []
        for proc in psutil.process_iter():
            if proc.name() == "ros2":
                processes.append(proc)
        
        ram_percent = 0
        ram_info = 0

        for proc in processes:
            ram_percent += proc.memory_percent()
            ram_info += proc.memory_info()[0]        
        return ram_percent, ram_info
    

    def ping(self, address_p):
        """
        Ping the desired address
        """
        res = subprocess.call(["ping", address_p, "-c1", "-W1"])
        if res > 0:
            return 0
        else:
            return 1


    def network_measure(self):
        """
        Measure the network usage
        """
        network_result = []

        self.new_network_data = psutil.net_io_counters()

        if self.old_network_data == None:
            self.old_network_data = self.new_network_data

        # Get sent bytes
        network_result.append(self.new_network_data.bytes_sent - self.old_network_data.bytes_sent)

        # Get received bytes
        network_result.append(self.new_network_data.bytes_recv - self.old_network_data.bytes_recv)

        # Get sent packets
        network_result.append(self.new_network_data.packets_sent - self.old_network_data.packets_sent)

        # Get received packets
        network_result.append(self.new_network_data.packets_recv - self.old_network_data.packets_recv)

        # Get errors while sending
        network_result.append(self.new_network_data.errout - self.old_network_data.errout)

        # Get errors while receiving
        network_result.append(self.new_network_data.errin - self.old_network_data.errin)

        # Get total number of incoming packets which were dropped
        network_result.append(self.new_network_data.dropin - self.old_network_data.dropin)

        # Get total number of outgoing packets which were dropped
        network_result.append(self.new_network_data.dropout - self.old_network_data.dropout)

        self.old_network_data = self.new_network_data

        return network_result


    def get_gps_data(self):
        """
        Get GPS data and store them in a list
        """
        # Open the serial port
        ser = serial.Serial(self.serial_location, self.serial_baudrate)
        try:
            received_data = False
            while received_data == False:
                # print("Waiting for GPS data...")
                line = ser.readline().decode().strip()
                if line.startswith("$GPGGA"): #GPS related data
                    received_data = True
                    data = line.split(',')
                    if len(data) > 9 and data[2] and data[4] and data[9]:
                        self.gps_data[0] = self.nmea_to_decimal_degrees(data[2], data[3])
                        self.gps_data[1] = self.nmea_to_decimal_degrees(data[4], data[5])
                        self.gps_data[2] = float(data[9])  # Altitude is directly in meters      
                    else:
                        print("Incomplete GPS data received.")
            return self.gps_data
        
        except Exception as e:
            print("No Serial connection:", e)
        
        finally:
            ser.close()


    # Function to convert NMEA coordinates to decimal degrees
    def nmea_to_decimal_degrees(self, coordinate, direction):
        degrees = int(float(coordinate) / 100)
        minutes = float(coordinate) - degrees * 100
        decimal_degrees = degrees + minutes / 60
        if direction in ['S', 'W']:
            decimal_degrees *= -1
        return decimal_degrees


    def get_data(self):
        """
        Get the measurement
        """
        start_time = time.time()
        stop = False
        while not stop:
            self.data = []
            network_result = self.network_measure()
            cpu_results = self.cpu_measure()
            ram_results = self.ram_measure()
            gps_data = self.get_gps_data()
            ping_target = self.ping(Config.TARGET_IP.value)
            
            #Timestamp
            self.data.append(int(round(time.time() * 1000)) - self.starting_time)
            
            #Network
            self.data.append(network_result[0])
            self.data.append(network_result[1])
            self.data.append(network_result[2])
            self.data.append(network_result[3])
            self.data.append(network_result[4])
            self.data.append(network_result[5])
            self.data.append(network_result[6])
            self.data.append(network_result[7])
            
            #CPU
            self.data.append(cpu_results[0])
            self.data.append(cpu_results[1])            
            
            #RAM
            self.data.append(ram_results[0])
            self.data.append(ram_results[1])

            #Ping
            if not self.is_target:
                self.data.append(ping_target)

            #GPS
            if gps_data:
                self.data.append(gps_data[0])
                self.data.append(gps_data[1])
                self.data.append(gps_data[2])
            
            self.write_csv()
            
            elapsed_time = time.time() - start_time
            if elapsed_time >= self.experiment_duration:
                stop=True
        
        print("Experiment concluded")
        self.write_csv()



if __name__ == "__main__":  
    parser = argparse.ArgumentParser(
                                description="Meta monitoring class. Used as an intermediate node to manage 'Monitoring' class",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("name", help="Experiment's name", type=str)
    parser.add_argument("duration", help="Experiment's duration", type=float)
    parser.add_argument("step", help="Experiment's timestep measure", type=float)
    parser.add_argument("is_target", help="Is the device the target ?", type=float)

    args = parser.parse_args()
    config = vars(args)
    
    monitoring = Monitoring(experiment_name_p=config['name'], 
                            experiment_duration_p=config['duration'], 
                            experiment_timestep_p=config['step'],
                            is_target_p=config['is_target'])
