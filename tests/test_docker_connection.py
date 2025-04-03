import sys
import os
import platform
import docker

def test_docker_connection():
    """Test Docker connectivity using various methods"""
    print("=== Testing Docker Connection ===")
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print(f"System: {platform.system()}")
    
    if platform.system() == "Linux":
        print(f"Linux release: {platform.uname().release}")
        print(f"WSL detected: {'microsoft' in platform.uname().release.lower()}")
    
    print(f"Current directory: {os.getcwd()}")
    print(f"Docker socket exists: {os.path.exists('/var/run/docker.sock')}")
    
    connection_methods = [
        ("Default", lambda: docker.from_env()),
        ("Unix Socket", lambda: docker.DockerClient(base_url='unix:///var/run/docker.sock')),
        ("TCP", lambda: docker.DockerClient(base_url='tcp://localhost:2375'))
    ]
    
    if platform.system() == "Windows":
        connection_methods.append(
            ("Windows Named Pipe", lambda: docker.DockerClient(base_url='npipe:////./pipe/docker_engine'))
        )
    
    for name, connector in connection_methods:
        print(f"\nTrying {name} connection method...")
        try:
            client = connector()
            version = client.version()
            print(f"✅ Connected successfully using {name} method!")
            print(f"Docker version: {version.get('Version', 'unknown')}")
            print(f"API version: {version.get('ApiVersion', 'unknown')}")
            
            # Try listing images as a further test
            images = client.images.list()
            print(f"Found {len(images)} images")
            return client  # Return the first working client
            
        except Exception as e:
            print(f"❌ {name} connection failed: {str(e)}")
    
    print("\n❌ All connection methods failed. Please ensure Docker is running and accessible.")
    return None

if __name__ == "__main__":
    client = test_docker_connection()
    
    if client:
        print("\n=== Testing image existence ===")
        try:
            image_name = "python-function:latest"
            try:
                image = client.images.get(image_name)
                print(f"✅ Image {image_name} found!")
            except docker.errors.ImageNotFound:
                print(f"❌ Image {image_name} not found. You need to build it first.")
                print("Run the build script in the docker directory.")
        except Exception as e:
            print(f"Error checking for image: {e}")
