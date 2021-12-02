import numpy as np

arr = [[-0.18885411,  0.49688898, -0.84701562]]
arr.append([-0.18669537,  0.53629687, -0.82312244])
arr.append([-0.19161231,  0.50092494, -0.8440136 ])
arr.append([-0.01043901,  0.45191402, -0.89200041])

mean = np.mean(arr, axis = 0)
std = np.std(arr, axis = 0)

filter = (abs(arr - mean) < std)
arr_filtered = []
for i in range(len(arr)):
    if filter[i].all():
        arr_filtered.append(arr[i])

estimated_vector = np.mean(arr_filtered, axis = 0)
print(estimated_vector)